"""End-to-end pipeline behaviour, including the contract the results UI reads."""

import pytest

from prds.config import Settings
from prds.kbsim.branches import BASELINE_SOURCE, STATE_SOURCE
from prds.kbsim.orchestrator import KbSimOrchestrator
from prds.llm.client import LLMClient
from prds.models.domain import (
    CurrentState,
    Rationality,
    SimulationConfig,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    TargetGoal,
)
from tests.kbsim_fakes import FakeLightRAG

BRANCHES = 4
EVENTS = 3


def _settings(**overrides) -> Settings:
    return Settings(openai_api_key="test-key", **overrides)


def _simulation_input(**config_overrides) -> SimulationInput:
    config = {
        "agent_count": BRANCHES,
        "max_events": EVENTS,
        "seed": 42,
        "kb_category_ids": ["math_kb"],
        **config_overrides,
    }
    return SimulationInput(
        current_state=CurrentState(background="学生数学 62 分，函数题薄弱。"),
        goal=TargetGoal(
            description="一年内把数学从 62 提到 78 分", success_metrics={"数学成绩": 78}
        ),
        config=SimulationConfig(**config),
    )


class Run:
    """One completed pipeline run plus everything observed while it ran."""

    def __init__(self) -> None:
        self.kb = FakeLightRAG()
        self.phases: list[SimulationPhase] = []
        self.events: list[tuple[int, int, int]] = []
        self.checkpoints: list[int] = []
        self.result: SimulationResult | None = None

    async def execute(self, settings: Settings | None = None, **config_overrides) -> SimulationResult:
        settings = settings or _settings()
        orchestrator = KbSimOrchestrator(LLMClient(settings), settings)
        orchestrator.kb = self.kb  # type: ignore[assignment]

        async def on_phase(phase, extra):
            self.phases.append(phase)

        async def on_event(index, alive, total):
            self.events.append((index, alive, total))

        async def checkpoint(index, states):
            self.checkpoints.append(index)

        self.result = await orchestrator.run(
            "sim-test-1",
            _simulation_input(**config_overrides),
            on_phase=on_phase,
            on_event=on_event,
            checkpoint=checkpoint,
        )
        return self.result


@pytest.fixture
async def run() -> Run:
    r = Run()
    await r.execute()
    return r


async def test_pipeline_walks_the_expected_phases(run: Run):
    assert run.phases == [
        SimulationPhase.INTAKE,
        SimulationPhase.EVENT_PLAN,
        SimulationPhase.BRANCH_FORK,
        SimulationPhase.BRANCH_SIM,
        SimulationPhase.SCORING,
        SimulationPhase.SYNTHESIS,
        SimulationPhase.COMPLETED,
    ]
    assert run.events == [(i, BRANCHES, EVENTS) for i in range(1, EVENTS + 1)]


async def test_pipeline_result_shape(run: Run):
    result = run.result
    assert result.agent_count == BRANCHES
    assert result.events_simulated == EVENTS
    assert len(result.planned_events) == EVENTS
    assert len(result.event_comparisons) == EVENTS
    assert len(result.agent_paths) == BRANCHES
    assert len(result.branches) == BRANCHES
    assert len(result.state_trace) == BRANCHES * EVENTS
    assert result.metric_specs
    assert result.champion_agent_id == result.branches[0].branch_id
    assert result.world_background.graph_source == "lightrag"
    assert result.world_background.research_provider == "knowledge_base"


async def test_event_comparisons_carry_everything_the_results_page_renders(run: Run):
    """Field-completeness guard for frontend/js/pages/results.js."""
    metric_names = {spec.name for spec in run.result.metric_specs}

    for index, comparison in enumerate(run.result.event_comparisons, start=1):
        assert comparison.event_index == index
        assert comparison.event_id and comparison.event_label
        assert comparison.world_summary
        assert comparison.events
        assert comparison.event_summaries
        for summary in comparison.event_summaries:
            assert summary.event_type and summary.description
            assert isinstance(summary.is_black_swan, bool)
            assert isinstance(summary.evidence, list)

        assert len(comparison.agents) == BRANCHES
        assert [a.rank for a in comparison.agents] == sorted(a.rank for a in comparison.agents)
        for agent in comparison.agents:
            assert agent.agent_id and agent.rank >= 1
            # Strategy chip + response block.
            assert agent.action and agent.decision and agent.reasoning
            # Predicted state block.
            assert agent.outcome
            assert agent.label
            assert agent.rationality in (Rationality.RATIONAL, Rationality.IRRATIONAL)
            # Metric readings bar.
            assert {m.name for m in agent.metrics} == metric_names
            assert all(m.unit for m in agent.metrics)
            assert set(agent.action_summary) == metric_names
            # Goal progress bar.
            assert 0.0 <= agent.goal_status.progress <= 1.0
            assert set(agent.goal_status.metric_progress) == metric_names


async def test_agent_paths_expose_one_step_per_event(run: Run):
    for path in run.result.agent_paths:
        assert path.label
        assert path.rank >= 1
        assert [step.event_index for step in path.steps] == list(range(1, EVENTS + 1))
        for step in path.steps:
            assert step.trigger_event_id and step.action and step.decision
            assert step.outcome
            assert step.world_summary


async def test_branch_summaries_are_ranked_and_expose_their_workspaces(run: Run):
    summaries = run.result.branches

    assert [s.rank for s in summaries] == list(range(1, BRANCHES + 1))
    progresses = [s.final_progress for s in summaries]
    assert progresses == sorted(progresses, reverse=True)
    for summary in summaries:
        assert summary.label and summary.persona
        assert summary.final_metrics
        assert summary.workspaces, "the graph viewer needs a browsable workspace"


async def test_run_keeps_a_rational_majority_with_one_irrational_branch(run: Run):
    rationalities = [s.rationality for s in run.result.branches]

    assert rationalities.count(Rationality.RATIONAL) == 3
    assert rationalities.count(Rationality.IRRATIONAL) == 1


async def test_original_knowledge_base_is_never_written_to(run: Run):
    writes = [
        kwargs.get("workspace")
        for name, _, kwargs in run.kb.calls
        if name in {"replace_document", "insert_text", "delete_document"}
    ]

    assert writes, "the pipeline must write state snapshots somewhere"
    assert "math_kb" not in writes
    assert all(w and w.startswith("sim_sim-test-1_b") for w in writes)


async def test_each_event_replaces_the_previous_state_snapshot(run: Run):
    replacements = run.kb.args_for("replace_document")
    baselines = [a for a, _ in replacements if a[0] == BASELINE_SOURCE]
    snapshots = [a for a, _ in replacements if a[0] == STATE_SOURCE]

    assert len(baselines) == BRANCHES
    assert len(snapshots) == BRANCHES * EVENTS

    # Within one branch, every round prunes the old snapshot before inserting.
    branch_ws = run.result.branches[0].workspaces[0]
    ordered = [
        name
        for name, _, kwargs in run.kb.calls
        if name in {"delete_document", "insert_text"} and kwargs.get("workspace") == branch_ws
    ]
    assert ordered[-2 * EVENTS :] == ["delete_document", "insert_text"] * EVENTS


async def test_branch_retrieval_reuses_precomputed_keywords():
    run = Run()
    await run.execute()

    retrievals = run.kb.args_for("retrieve_context")

    assert len(retrievals) == BRANCHES * EVENTS
    for _, kwargs in retrievals:
        assert kwargs["hl_keywords"], "keywords are extracted once per event, not per branch"
        assert kwargs["ll_keywords"]


async def test_reindex_interval_reduces_write_back_rounds():
    run = Run()
    await run.execute(settings=_settings(prds_kbsim_reindex_every=2), max_events=4)

    snapshots = [a for a, _ in run.kb.args_for("replace_document") if a[0] == STATE_SOURCE]

    # Events 2 and 4 only: every other event plus always the last one.
    assert len(snapshots) == BRANCHES * 2


async def test_branches_are_kept_for_graph_browsing_by_default(run: Run):
    assert SimulationPhase.CLEANUP not in run.phases
    assert run.kb.args_for("delete_workspace") == []
    assert run.kb.workspaces


async def test_branches_are_removed_when_keeping_is_disabled():
    run = Run()
    await run.execute(settings=_settings(prds_kbsim_keep_branches=False))

    assert SimulationPhase.CLEANUP in run.phases
    assert len(run.kb.args_for("delete_workspace")) == BRANCHES
    assert run.kb.workspaces == {}


async def test_synthesis_and_distribution_are_populated(run: Run):
    result = run.result

    assert result.synthesis.recommended_roadmap
    assert result.synthesis.principles
    assert result.counterfactuals
    assert result.outcome_distribution.sample_size == BRANCHES
    assert result.outcome_distribution.metric_bands


async def test_long_run_marks_black_swan_events_for_the_ui():
    run = Run()
    await run.execute(max_events=24)

    planned = run.result.planned_events
    swans = [e for e in planned if e.is_black_swan]

    assert 1 <= len(swans) <= 3
    assert run.checkpoints == [5, 10, 15, 20]
    flagged = [
        summary
        for comparison in run.result.event_comparisons
        for summary in comparison.event_summaries
        if summary.is_black_swan
    ]
    assert len(flagged) == len(swans)


async def test_run_without_a_knowledge_base_still_completes():
    run = Run()
    settings = _settings()
    orchestrator = KbSimOrchestrator(LLMClient(settings), settings)
    orchestrator.kb = run.kb  # type: ignore[assignment]

    simulation_input = _simulation_input()
    simulation_input.config.kb_category_ids = []

    result = await orchestrator.run("sim-test-2", simulation_input)

    assert result.events_simulated == EVENTS
    assert len(result.branches) == BRANCHES
    assert run.kb.args_for("copy_workspace") == []
    assert len(run.kb.args_for("create_workspace")) == BRANCHES
