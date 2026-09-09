"""Knowledge-base branch simulation orchestrator.

Walks the planned timeline once, advancing every strategy branch in parallel at
each event: retrieve from the branch's own KB, pick a strategy, predict the next
state, then write that state back into the branch KB (replacing the previous
snapshot and its graph slice) so the next event sees an evolved world.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from prds.config import Settings, get_settings
from prds.kb.client import LightRAGClient
from prds.kbsim.branches import BranchManager
from prds.kbsim.events import event_keywords, plan_events
from prds.kbsim.intake import IntakeBrief, build_intake_brief
from prds.kbsim.state import (
    baseline_state,
    predict_state,
    render_baseline_snapshot,
    render_state_snapshot,
)
from prds.kbsim.strategies import generate_strategies
from prds.kbsim.synthesis import build_distribution, build_synthesis, rank_branches
from prds.llm.client import LLMClient
from prds.models.domain import (
    AgentDecisionPath,
    BranchProfile,
    BranchStateUpdate,
    DecisionStep,
    Event,
    EventAgentDecision,
    EventComparison,
    EventSummary,
    OntologyGraph,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    StateTraceEntry,
    StrategyOption,
    TargetGoal,
    WorldBackground,
)
from prds.simulation.control import get_control

logger = logging.getLogger(__name__)

PhaseCallback = Callable[[SimulationPhase, dict[str, Any]], Awaitable[None]]


def _rag_storage_dir() -> Path | None:
    """Where LightRAG keeps its per-workspace directories, if discoverable."""
    candidate = Path("./data/lightrag/rag_storage").resolve()
    return candidate if candidate.is_dir() else None


class KbSimOrchestrator:
    """Runs the KB-grounded, branch-parallel simulation end to end."""

    def __init__(self, llm: LLMClient, settings: Settings | None = None) -> None:
        self.llm = llm
        self.settings = settings or get_settings()
        self.kb = LightRAGClient(self.settings)

    async def run(
        self,
        simulation_id: str,
        simulation_input: SimulationInput,
        *,
        on_phase: PhaseCallback | None = None,
        on_event: Callable[[int, int, int], Awaitable[None]] | None = None,
        checkpoint: Callable[[int, list[BranchStateUpdate]], Awaitable[None]] | None = None,
        on_pause: Callable[[], Awaitable[None]] | None = None,
        on_resume: Callable[[], Awaitable[None]] | None = None,
    ) -> SimulationResult:
        config = simulation_input.config
        current_state = simulation_input.current_state
        goal = simulation_input.goal
        control = get_control()
        model = config.llm_model or None
        analysis_model = config.llm_model_analysis or self.llm.analysis_model

        branch_count = max(1, config.agent_count)
        source_ids = [c for c in (config.kb_category_ids or []) if c]

        async def phase(p: SimulationPhase, extra: dict[str, Any] | None = None) -> None:
            if on_phase:
                await on_phase(p, extra or {})

        # ---------- intake ----------
        await phase(SimulationPhase.INTAKE)
        kb_context = ""
        if source_ids:
            try:
                kb_context = await self.kb.query_contexts(goal.description, source_ids)
            except Exception as exc:
                logger.warning("Initial KB retrieval failed: %s", exc)
        brief = await build_intake_brief(
            self.llm, goal=goal, current_state=current_state, kb_context=kb_context
        )
        specs = brief.metric_specs

        # ---------- event planning ----------
        await phase(SimulationPhase.EVENT_PLAN)
        events = await plan_events(
            self.llm,
            goal=goal,
            brief=brief,
            config=config,
            kb_context=kb_context,
            settings=self.settings,
        )
        total_events = len(events)

        # ---------- fork branches ----------
        await phase(SimulationPhase.BRANCH_FORK, {"branch_count": branch_count})
        manager = BranchManager(
            self.kb,
            self.settings,
            simulation_id=simulation_id,
            rag_storage_dir=_rag_storage_dir(),
        )
        baseline_doc = render_baseline_snapshot(
            goal=goal,
            background=brief.background,
            specs=specs,
            constraints=brief.constraints,
        )
        branches = await manager.fork(
            branch_count=branch_count,
            source_ids=source_ids,
            baseline_doc=baseline_doc,
        )

        states: dict[str, BranchStateUpdate] = {
            b.branch_id: baseline_state(b, specs, brief.background) for b in branches
        }
        trace: list[StateTraceEntry] = []
        comparisons: list[EventComparison] = []

        # ---------- timeline ----------
        await phase(SimulationPhase.BRANCH_SIM)
        for event_index, event in enumerate(events, start=1):
            injected = control.pop_user_events(simulation_id, event_index)
            comparison = await self._advance_event(
                manager=manager,
                branches=branches,
                states=states,
                trace=trace,
                event=event,
                extra_events=injected,
                event_index=event_index,
                total_events=total_events,
                goal=goal,
                brief=brief,
                model=model,
                analysis_model=analysis_model,
            )
            comparisons.append(comparison)

            if on_event:
                await on_event(event_index, len(branches), total_events)
            if checkpoint and event_index % 5 == 0:
                await checkpoint(event_index, list(states.values()))
            if event_index < total_events:
                await control.maybe_pause_after_event(
                    simulation_id,
                    on_pause or (lambda: asyncio.sleep(0)),
                    on_resume or (lambda: asyncio.sleep(0)),
                )

        # ---------- scoring & synthesis ----------
        await phase(SimulationPhase.SCORING)
        summaries = rank_branches(branches, states)
        rank_by_branch = {s.branch_id: s.rank for s in summaries}
        self._apply_ranks(comparisons, rank_by_branch)
        distribution = build_distribution(states, specs)

        await phase(SimulationPhase.SYNTHESIS)
        synthesis, counterfactuals = await build_synthesis(
            self.llm,
            goal=goal,
            trace=trace,
            summaries=summaries,
            specs=specs,
            model=analysis_model,
        )

        if not self.settings.prds_kbsim_keep_branches:
            await phase(SimulationPhase.CLEANUP)
            await manager.cleanup(branches)

        await phase(SimulationPhase.COMPLETED)

        champion = summaries[0].branch_id if summaries else ""
        return SimulationResult(
            simulation_id=simulation_id,
            domain_id=config.domain_id,
            agent_count=len(branches),
            events_simulated=total_events,
            ontology=OntologyGraph(
                risks=brief.risks,
                opportunities=brief.opportunities,
                constraints=brief.constraints,
                targets=[goal.description],
            ),
            champion_agent_id=champion,
            agent_paths=self._build_paths(branches, trace, rank_by_branch, comparisons),
            event_comparisons=comparisons,
            planned_events=events,
            world_background=WorldBackground(
                summary=brief.background,
                risks=brief.risks,
                opportunities=brief.opportunities,
                graph_source="lightrag",
                research_provider="knowledge_base",
                research_report=brief.notes,
            ),
            counterfactuals=counterfactuals,
            synthesis=synthesis,
            outcome_distribution=distribution,
            branches=summaries,
            metric_specs=specs,
            state_trace=trace,
        )

    # ------------------------------------------------------------------

    async def _advance_event(
        self,
        *,
        manager: BranchManager,
        branches: list[BranchProfile],
        states: dict[str, BranchStateUpdate],
        trace: list[StateTraceEntry],
        event: Event,
        extra_events: list[Event],
        event_index: int,
        total_events: int,
        goal: TargetGoal,
        brief: IntakeBrief,
        model: str | None,
        analysis_model: str | None,
    ) -> EventComparison:
        """One event across every branch: retrieve, decide, predict, write back."""
        batch = [event, *extra_events]
        query = self._retrieval_query(batch, goal)
        hl, ll = event_keywords(event, brief)

        # Retrieval for all branches in parallel; keywords are computed once so
        # LightRAG can skip its own keyword-extraction call per branch.
        retrieved = await asyncio.gather(
            *(
                manager.retrieve(branch, query, hl_keywords=hl, ll_keywords=ll)
                for branch in branches
            ),
            return_exceptions=True,
        )
        contexts = {
            branch.branch_id: ("" if isinstance(ctx, BaseException) else ctx)
            for branch, ctx in zip(branches, retrieved)
        }

        strategies = await generate_strategies(
            self.llm,
            event=event,
            event_index=event_index,
            total_events=total_events,
            goal=goal,
            branches=branches,
            metric_specs=brief.metric_specs,
            contexts=contexts,
            last_states=states,
            model=analysis_model,
        )

        predictions = await asyncio.gather(
            *(
                predict_state(
                    self.llm,
                    branch=branch,
                    event=event,
                    event_index=event_index,
                    total_events=total_events,
                    strategy=strategies[branch.branch_id],
                    previous=states[branch.branch_id],
                    specs=brief.metric_specs,
                    goal=goal,
                    context=contexts.get(branch.branch_id, ""),
                    model=model,
                )
                for branch in branches
            )
        )

        decisions: list[EventAgentDecision] = []
        for branch, prediction in zip(branches, predictions):
            strategy = strategies[branch.branch_id]
            states[branch.branch_id] = prediction
            trace.append(
                StateTraceEntry(
                    event_index=event_index,
                    event_id=event.event_id,
                    branch_id=branch.branch_id,
                    strategy=strategy,
                    state=prediction,
                )
            )
            decisions.append(self._to_decision(branch, strategy, prediction))

        # Rebuild each branch's knowledge base around its new state.
        if manager.should_reindex(event_index, total_events):
            snapshots = [
                render_state_snapshot(
                    branch=branch,
                    goal=goal,
                    event=event,
                    event_index=event_index,
                    strategy=strategies[branch.branch_id],
                    state=states[branch.branch_id],
                )
                for branch in branches
            ]
            await asyncio.gather(
                *(
                    manager.write_state(branch, snapshot)
                    for branch, snapshot in zip(branches, snapshots)
                ),
                return_exceptions=True,
            )

        return EventComparison(
            event_index=event_index,
            event_id=event.event_id,
            event_label=f"事件 {event_index}",
            world_summary=self._world_summary(batch, event_index, total_events),
            events=[e.event_type for e in batch],
            event_summaries=[
                EventSummary(
                    event_type=e.event_type,
                    description=e.description,
                    impact=e.impact,
                    is_black_swan=e.is_black_swan,
                    evidence=e.evidence,
                )
                for e in batch
            ],
            agents=decisions,
        )

    @staticmethod
    def _retrieval_query(batch: list[Event], goal: TargetGoal) -> str:
        descriptions = "；".join(e.description for e in batch if e.description)
        return (
            f"围绕目标「{goal.description}」，与下面处境相关的事实、历史记录、"
            f"可用资源与已知规律：{descriptions}"
        )

    @staticmethod
    def _world_summary(batch: list[Event], event_index: int, total_events: int) -> str:
        parts = [f"第 {event_index}/{total_events} 个事件节点。"]
        for e in batch:
            marker = "【黑天鹅】" if e.is_black_swan else ""
            parts.append(f"{marker}{e.description}")
            if e.evidence:
                parts.append(f"（依据：{'；'.join(e.evidence)}）")
        return " ".join(parts)

    @staticmethod
    def _to_decision(
        branch: BranchProfile, strategy: StrategyOption, state: BranchStateUpdate
    ) -> EventAgentDecision:
        outcome = state.narrative
        if state.side_effects:
            outcome = f"{outcome}\n副作用：{'；'.join(state.side_effects)}"
        return EventAgentDecision(
            agent_id=branch.branch_id,
            action=strategy.action_label,
            decision=strategy.title,
            reasoning=" ".join(p for p in (strategy.detail, strategy.rationale) if p),
            outcome=outcome,
            success=state.success,
            label=branch.label,
            rationality=branch.rationality,
            metrics=state.metrics,
            action_summary={
                m.name: round(m.value - m.previous, 4) for m in state.metrics
            },
            goal_status=state.goal_status,
        )

    @staticmethod
    def _apply_ranks(
        comparisons: list[EventComparison], rank_by_branch: dict[str, int]
    ) -> None:
        for comparison in comparisons:
            for decision in comparison.agents:
                decision.rank = rank_by_branch.get(decision.agent_id, 0)
            comparison.agents.sort(key=lambda d: (d.rank or 999, d.agent_id))

    @staticmethod
    def _build_paths(
        branches: list[BranchProfile],
        trace: list[StateTraceEntry],
        rank_by_branch: dict[str, int],
        comparisons: list[EventComparison],
    ) -> list[AgentDecisionPath]:
        summary_by_event = {c.event_index: c for c in comparisons}
        by_branch: dict[str, list[StateTraceEntry]] = {}
        for entry in trace:
            by_branch.setdefault(entry.branch_id, []).append(entry)

        paths: list[AgentDecisionPath] = []
        for branch in branches:
            entries = by_branch.get(branch.branch_id, [])
            steps = []
            for entry in entries:
                comparison = summary_by_event.get(entry.event_index)
                steps.append(
                    DecisionStep(
                        event_index=entry.event_index,
                        trigger_event_id=entry.event_id,
                        world_summary=comparison.world_summary if comparison else "",
                        events=comparison.events if comparison else [],
                        action=entry.strategy.action_label,
                        decision=entry.strategy.title,
                        reasoning=entry.strategy.rationale,
                        outcome=entry.state.narrative,
                        success=entry.state.success,
                        action_summary={
                            m.name: round(m.value - m.previous, 4)
                            for m in entry.state.metrics
                        },
                        goal_status=entry.state.goal_status,
                    )
                )
            final_progress = entries[-1].state.goal_status.progress if entries else 0.0
            paths.append(
                AgentDecisionPath(
                    agent_id=branch.branch_id,
                    rank=rank_by_branch.get(branch.branch_id, 0),
                    total_score=round(final_progress, 4),
                    label=branch.label,
                    rationality=branch.rationality,
                    steps=steps,
                )
            )
        paths.sort(key=lambda p: (p.rank or 999, p.agent_id))
        return paths
