"""Branch lifecycle: fork the knowledge base once per response strategy.

Each branch owns copies of the selected workspaces, so it can evolve its own
graph without ever touching the user's originals. Copies are filesystem-level
clones on the LightRAG side, which avoids re-indexing the documents N times.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path

from prds.config import Settings
from prds.kb.client import LightRAGClient, normalize_workspace_id
from prds.models.domain import BranchProfile, Rationality

logger = logging.getLogger(__name__)

STATE_SOURCE = "prds_branch_state.md"
BASELINE_SOURCE = "prds_branch_baseline.md"

RATIONAL_PERSONAS = [
    "循证稳健：先看数据与可行性，成本可控、可持续，动作幅度适中",
    "结构化推进：把目标拆成小步骤，按周推进并复盘",
    "资源约束优先：在不打破现有时间与预算安排的前提下改进",
    "专业外援：优先借助已有的专业资源，把关键环节交给更擅长的人",
    "复盘驱动：每轮只改一个变量，用结果决定下一步",
    "长期主义：牺牲短期速度换取习惯与基础的稳固",
]

IRRATIONAL_PERSONAS = [
    "全力压注：把绝大部分资源砸向单一指标，忽视副作用",
    "情绪驱动：被焦虑推着走，频繁更换方法且不等结果",
    "回避拖延：认为问题会自己好转，实质上不采取有效动作",
]


def rationality_split(count: int, ratio: float) -> list[Rationality]:
    """Rational majority, irrational minority — at least one of each when N>=3."""
    if count <= 0:
        return []
    if count == 1:
        return [Rationality.RATIONAL]
    rational = int(math.ceil(count * max(0.0, min(1.0, ratio))))
    rational = max(1, min(count, rational))
    if count >= 3 and rational == count:
        rational = count - 1
    if count == 2:
        rational = 1
    return [Rationality.RATIONAL] * rational + [Rationality.IRRATIONAL] * (count - rational)


def _persona_for(rationality: Rationality, ordinal: int) -> str:
    pool = RATIONAL_PERSONAS if rationality is Rationality.RATIONAL else IRRATIONAL_PERSONAS
    return pool[ordinal % len(pool)]


def _dir_size_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


class BranchManager:
    """Creates, updates, and tears down the per-strategy knowledge bases."""

    def __init__(
        self,
        client: LightRAGClient,
        settings: Settings,
        *,
        simulation_id: str,
        rag_storage_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.simulation_id = simulation_id
        self.rag_storage_dir = rag_storage_dir
        self._semaphore = asyncio.Semaphore(
            max(1, settings.prds_kbsim_max_concurrent_branches)
        )
        self.forked = True

    # ---------- fork ----------

    def _should_fork(self, source_ids: list[str]) -> bool:
        if not source_ids:
            return True
        if self.rag_storage_dir is None:
            return True
        total = sum(_dir_size_bytes(self.rag_storage_dir / sid) for sid in source_ids)
        if total > self.settings.prds_kbsim_max_fork_bytes:
            logger.warning(
                "Source knowledge bases are %.1f MB; skipping per-branch copies and "
                "reading the originals instead.",
                total / (1024 * 1024),
            )
            return False
        return True

    def _branch_workspace_id(self, branch_index: int, source_id: str) -> str:
        sim = normalize_workspace_id(self.simulation_id)[:18]
        return normalize_workspace_id(f"sim_{sim}_b{branch_index:02d}_{source_id}")[:64]

    async def fork(
        self, *, branch_count: int, source_ids: list[str], baseline_doc: str
    ) -> list[BranchProfile]:
        sources = [s for s in (source_ids or []) if s]
        self.forked = self._should_fork(sources)
        splits = rationality_split(branch_count, self.settings.prds_kbsim_rational_ratio)

        branches: list[BranchProfile] = []
        seen_rational = 0
        seen_irrational = 0
        for index, rationality in enumerate(splits, start=1):
            if rationality is Rationality.RATIONAL:
                persona = _persona_for(rationality, seen_rational)
                seen_rational += 1
            else:
                persona = _persona_for(rationality, seen_irrational)
                seen_irrational += 1
            branch_id = f"branch_{index:02d}"
            branches.append(
                BranchProfile(
                    branch_id=branch_id,
                    label=f"策略 {index}",
                    index=index,
                    rationality=rationality,
                    persona=persona,
                )
            )

        await asyncio.gather(
            *(self._prepare_branch(b, sources, baseline_doc) for b in branches)
        )
        logger.info(
            "Forked %d branches (%d rational / %d irrational), copies=%s",
            len(branches),
            seen_rational,
            seen_irrational,
            self.forked,
        )
        return branches

    async def _prepare_branch(
        self, branch: BranchProfile, sources: list[str], baseline_doc: str
    ) -> None:
        async with self._semaphore:
            if self.forked and sources:
                copies: list[str] = []
                for source_id in sources:
                    target = self._branch_workspace_id(branch.index, source_id)
                    try:
                        await self.client.copy_workspace(
                            source_id, target, f"{branch.label} · {source_id}"
                        )
                        copies.append(target)
                    except Exception as exc:
                        logger.warning(
                            "Failed to copy workspace %s for %s: %s",
                            source_id,
                            branch.branch_id,
                            exc,
                        )
                if copies:
                    branch.workspaces = copies
                    branch.primary_workspace = copies[0]
                else:
                    # Copying failed everywhere: fall back to reading the originals.
                    self.forked = False

            if not branch.primary_workspace:
                # Either nothing was selected or forking was skipped: the branch
                # gets a small private workspace that only holds its state, and
                # reads the untouched sources alongside it.
                target = self._branch_workspace_id(branch.index, "state")
                try:
                    await self.client.create_workspace(target, f"{branch.label} · state")
                    branch.primary_workspace = target
                    branch.workspaces = [target]
                except Exception as exc:
                    logger.warning(
                        "Failed to create state workspace for %s: %s", branch.branch_id, exc
                    )
                branch.read_only_workspaces = list(sources)

            if branch.primary_workspace and baseline_doc.strip():
                try:
                    await self.client.replace_document(
                        baseline_doc,
                        BASELINE_SOURCE,
                        workspace=branch.primary_workspace,
                        timeout=self.settings.prds_kbsim_index_timeout_s,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to seed baseline into %s: %s", branch.primary_workspace, exc
                    )

    # ---------- retrieval ----------

    def read_workspaces(self, branch: BranchProfile) -> list[str]:
        return [w for w in [*branch.workspaces, *branch.read_only_workspaces] if w]

    async def retrieve(
        self,
        branch: BranchProfile,
        query: str,
        *,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> str:
        workspaces = self.read_workspaces(branch)
        if not workspaces:
            return ""
        async with self._semaphore:
            return await self.client.retrieve_context(
                query,
                workspaces,
                max_chars=self.settings.prds_kbsim_retrieval_chars,
                hl_keywords=hl_keywords,
                ll_keywords=ll_keywords,
            )

    # ---------- state write-back ----------

    async def write_state(self, branch: BranchProfile, snapshot: str) -> bool:
        """Replace the branch's state snapshot, pruning the previous graph slice."""
        if not branch.primary_workspace or not snapshot.strip():
            return False
        async with self._semaphore:
            try:
                return await self.client.replace_document(
                    snapshot,
                    STATE_SOURCE,
                    workspace=branch.primary_workspace,
                    timeout=self.settings.prds_kbsim_index_timeout_s,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to write state snapshot into %s: %s",
                    branch.primary_workspace,
                    exc,
                )
                return False

    def should_reindex(self, event_index: int, total_events: int) -> bool:
        """Write back every N events, always on the final one."""
        every = max(1, self.settings.prds_kbsim_reindex_every)
        return event_index % every == 0 or event_index == total_events

    # ---------- teardown ----------

    async def cleanup(self, branches: list[BranchProfile]) -> None:
        """Drop branch workspaces (kept by default so their graphs stay browsable)."""
        targets = [w for b in branches for w in b.workspaces]
        if not targets:
            return
        results = await asyncio.gather(
            *(self.client.delete_workspace(w) for w in targets), return_exceptions=True
        )
        for target, result in zip(targets, results):
            if isinstance(result, Exception):
                logger.warning("Failed to delete branch workspace %s: %s", target, result)


async def delete_simulation_branches(
    client: LightRAGClient, simulation_id: str
) -> list[str]:
    """Remove every branch workspace belonging to a simulation."""
    prefix = f"sim_{normalize_workspace_id(simulation_id)[:18]}_b"
    try:
        workspaces = await client.list_workspaces()
    except Exception as exc:
        logger.warning("Could not list workspaces for cleanup: %s", exc)
        return []
    targets = [
        str(w.get("id"))
        for w in workspaces
        if isinstance(w, dict) and str(w.get("id", "")).startswith(prefix)
    ]
    results = await asyncio.gather(
        *(client.delete_workspace(t) for t in targets), return_exceptions=True
    )
    deleted = [t for t, r in zip(targets, results) if not isinstance(r, Exception)]
    return deleted
