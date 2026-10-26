"""Branch forking, state write-back and teardown."""

import pytest

from prds.config import Settings
from prds.kbsim.branches import (
    BASELINE_SOURCE,
    STATE_SOURCE,
    BranchManager,
    delete_simulation_branches,
    rationality_split,
)
from prds.models.domain import Rationality
from tests.kbsim_fakes import FakeLightRAG


def _settings(**overrides) -> Settings:
    return Settings(openai_api_key="test-key", **overrides)


def _manager(kb: FakeLightRAG, *, settings: Settings | None = None, storage=None) -> BranchManager:
    return BranchManager(
        kb,
        settings or _settings(),
        simulation_id="sim-abc-123",
        rag_storage_dir=storage,
    )


@pytest.mark.parametrize(
    "count,expected_rational",
    [(1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (8, 6), (10, 7)],
)
def test_rationality_split_keeps_rational_majority(count, expected_rational):
    split = rationality_split(count, 0.7)

    assert len(split) == count
    assert split.count(Rationality.RATIONAL) == expected_rational


@pytest.mark.parametrize("count", [3, 4, 6, 12])
def test_rationality_split_always_leaves_one_irrational(count):
    split = rationality_split(count, 0.7)

    assert Rationality.IRRATIONAL in split
    assert split.count(Rationality.RATIONAL) > split.count(Rationality.IRRATIONAL)


def test_rationality_split_extreme_ratios_stay_in_range():
    assert rationality_split(4, 1.0).count(Rationality.RATIONAL) == 3
    assert rationality_split(4, 0.0).count(Rationality.RATIONAL) == 1
    assert rationality_split(0, 0.7) == []


async def test_fork_copies_every_selected_kb_per_branch():
    kb = FakeLightRAG()
    manager = _manager(kb)

    branches = await manager.fork(
        branch_count=3, source_ids=["math_kb", "notes_kb"], baseline_doc="# 推演起点"
    )

    assert len(branches) == 3
    copies = kb.args_for("copy_workspace")
    assert len(copies) == 6  # 3 branches x 2 source KBs
    # Originals are only ever read from, never used as a copy target.
    assert {args[0] for args, _ in copies} == {"math_kb", "notes_kb"}
    assert all(args[1] not in {"math_kb", "notes_kb"} for args, _ in copies)
    # Workspace ids stay unique and identify both the simulation and the branch.
    targets = [args[1] for args, _ in copies]
    assert len(set(targets)) == 6
    assert all(t.startswith("sim_sim-abc-123_b") for t in targets)
    assert {t.split("_b")[1][:2] for t in targets} == {"01", "02", "03"}

    for branch in branches:
        assert len(branch.workspaces) == 2
        assert branch.primary_workspace == branch.workspaces[0]
        assert branch.read_only_workspaces == []


async def test_fork_seeds_baseline_into_each_branch():
    kb = FakeLightRAG()
    manager = _manager(kb)

    branches = await manager.fork(
        branch_count=2, source_ids=["math_kb"], baseline_doc="# 推演起点"
    )

    seeded = kb.args_for("replace_document")
    assert [args[0] for args, _ in seeded] == [BASELINE_SOURCE, BASELINE_SOURCE]
    assert {kwargs["workspace"] for _, kwargs in seeded} == {
        b.primary_workspace for b in branches
    }


async def test_fork_without_knowledge_base_creates_state_only_workspaces():
    kb = FakeLightRAG()
    manager = _manager(kb)

    branches = await manager.fork(branch_count=2, source_ids=[], baseline_doc="# 起点")

    assert kb.args_for("copy_workspace") == []
    assert len(kb.args_for("create_workspace")) == 2
    assert all(b.primary_workspace for b in branches)


async def test_fork_falls_back_to_shared_originals_when_too_large(tmp_path):
    storage = tmp_path / "rag_storage"
    source = storage / "math_kb"
    source.mkdir(parents=True)
    (source / "graph.graphml").write_bytes(b"x" * 4096)

    kb = FakeLightRAG()
    manager = _manager(
        kb,
        settings=_settings(prds_kbsim_max_fork_bytes=1024),
        storage=storage,
    )

    branches = await manager.fork(
        branch_count=2, source_ids=["math_kb"], baseline_doc="# 起点"
    )

    assert manager.forked is False
    assert kb.args_for("copy_workspace") == []
    for branch in branches:
        # Reads the untouched original alongside its own small state workspace.
        assert branch.read_only_workspaces == ["math_kb"]
        assert branch.primary_workspace not in {"math_kb"}
        assert manager.read_workspaces(branch) == [
            branch.primary_workspace,
            "math_kb",
        ]


async def test_write_state_replaces_the_previous_snapshot():
    kb = FakeLightRAG()
    manager = _manager(kb)
    branches = await manager.fork(
        branch_count=1, source_ids=["math_kb"], baseline_doc=""
    )
    branch = branches[0]

    assert await manager.write_state(branch, "# 状态快照 1")
    assert await manager.write_state(branch, "# 状态快照 2")

    state_writes = [
        (name, kwargs)
        for name, _, kwargs in kb.calls
        if name in {"delete_document", "insert_text"}
    ]
    # Each round prunes the previous snapshot before inserting the new one.
    assert [name for name, _ in state_writes] == [
        "delete_document",
        "insert_text",
        "delete_document",
        "insert_text",
    ]
    assert kb.documents[branch.primary_workspace][STATE_SOURCE] == "# 状态快照 2"


async def test_write_state_requires_a_target_workspace():
    kb = FakeLightRAG()
    manager = _manager(kb)
    branches = await manager.fork(branch_count=1, source_ids=[], baseline_doc="")
    branches[0].primary_workspace = ""

    from prds.simulation.errors import SimulationFailure
    with pytest.raises(SimulationFailure):
        await manager.write_state(branches[0], "# 快照")
    with pytest.raises(SimulationFailure):
        await manager.write_state(branches[0], "   ")


@pytest.mark.parametrize(
    "every,index,total,expected",
    [(1, 1, 5, True), (1, 5, 5, True), (2, 1, 5, False), (2, 2, 5, True), (2, 5, 5, True)],
)
def test_should_reindex_honours_the_configured_interval(every, index, total, expected):
    manager = _manager(FakeLightRAG(), settings=_settings(prds_kbsim_reindex_every=every))

    assert manager.should_reindex(index, total) is expected


async def test_cleanup_removes_only_branch_workspaces():
    kb = FakeLightRAG()
    kb.workspaces["math_kb"] = "原始知识库"
    manager = _manager(kb)
    branches = await manager.fork(
        branch_count=2, source_ids=["math_kb"], baseline_doc=""
    )

    await manager.cleanup(branches)

    assert "math_kb" in kb.workspaces
    assert not [w for w in kb.workspaces if w != "math_kb"]


async def test_delete_simulation_branches_matches_only_its_own_prefix():
    kb = FakeLightRAG()
    manager = _manager(kb)
    await manager.fork(branch_count=2, source_ids=["math_kb"], baseline_doc="")
    kb.workspaces["math_kb"] = "原始知识库"
    kb.workspaces["sim_other-run_b01_math_kb"] = "另一次推演"

    deleted = await delete_simulation_branches(kb, "sim-abc-123")

    assert len(deleted) == 2
    assert "math_kb" in kb.workspaces
    assert "sim_other-run_b01_math_kb" in kb.workspaces
