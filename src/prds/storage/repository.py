import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prds.config import Settings, get_settings
from prds.models.domain import (
    AgentDecisionPath,
    AgentState,
    EventSummary,
    SimulationInput,
    SimulationPhase,
    SimulationProgress,
    SimulationResult,
    SimulationStatus,
    UserEventInput,
    WorldState,
)
from prds.simulation.control import get_control
from prds.analysis.scoring import rank_agents
from prds.analysis.trajectory import (
    build_agent_decision_paths,
    build_period_comparisons,
    build_period_comparisons_from_agents,
)
from prds.utils.time_labels import compute_period_label, time_config_dict
from prds.storage.models import Base, SimulationRun


class SimulationRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_async_engine(self.settings.prds_database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def create_run(self, simulation_input: SimulationInput) -> str:
        run_id = str(uuid.uuid4())
        config = simulation_input.config
        async with self.session_factory() as session:
            run = SimulationRun(
                id=run_id,
                status=SimulationStatus.PENDING.value,
                phase=SimulationPhase.PENDING.value,
                total_periods=config.periods,
                total_agents=config.agent_count,
                alive_agents=config.agent_count,
                input_json=simulation_input.model_dump_json(),
            )
            session.add(run)
            await session.commit()
        return run_id

    async def update_progress(
        self,
        run_id: str,
        *,
        status: SimulationStatus | None = None,
        phase: SimulationPhase | None = None,
        current_period: int | None = None,
        alive_agents: int | None = None,
        progress_pct: float | None = None,
        error: str | None = None,
    ) -> None:
        async with self.session_factory() as session:
            run = await session.get(SimulationRun, run_id)
            if not run:
                return
            if status:
                run.status = status.value
            if phase:
                run.phase = phase.value
            if current_period is not None:
                run.current_period = current_period
            if alive_agents is not None:
                run.alive_agents = alive_agents
            if progress_pct is not None:
                run.progress_pct = progress_pct
            run.updated_at = datetime.now(timezone.utc)
            if error is not None:
                run.error = error
            await session.commit()

    async def save_result(self, run_id: str, result: SimulationResult) -> None:
        async with self.session_factory() as session:
            run = await session.get(SimulationRun, run_id)
            if not run:
                return
            run.result_json = result.model_dump_json()
            run.status = SimulationStatus.COMPLETED.value
            run.phase = SimulationPhase.COMPLETED.value
            run.progress_pct = 100.0
            run.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def get_run(self, run_id: str) -> SimulationRun | None:
        async with self.session_factory() as session:
            return await session.get(SimulationRun, run_id)

    async def _time_config_for_run(self, run_id: str, result: SimulationResult | None) -> dict:
        if result and getattr(result, "period_time_unit", None):
            return time_config_dict(
                unit=result.period_time_unit,
                length=result.period_time_length,
                start_date=result.simulation_start_date,
            )
        sim_input = await self.get_input(run_id)
        if sim_input:
            cfg = sim_input.config
            return time_config_dict(
                unit=cfg.period_time_unit,
                length=cfg.period_time_length,
                start_date=cfg.simulation_start_date,
            )
        return time_config_dict()

    async def get_progress(self, run_id: str) -> SimulationProgress | None:
        run = await self.get_run(run_id)
        if not run:
            return None
        control = get_control()
        time_cfg = await self._time_config_for_run(run_id, await self.get_result(run_id))
        return SimulationProgress(
            simulation_id=run.id,
            status=SimulationStatus(run.status),
            phase=SimulationPhase(run.phase),
            current_period=run.current_period,
            total_periods=run.total_periods,
            alive_agents=run.alive_agents,
            total_agents=run.total_agents,
            progress_pct=run.progress_pct,
            error=run.error,
            pause_pending=control.is_pause_requested(run_id),
            pending_user_events=control.pending_event_count(run_id),
            period_time_unit=time_cfg["period_time_unit"],
            period_time_length=time_cfg["period_time_length"],
            simulation_start_date=time_cfg["simulation_start_date"],
        )

    async def get_result(self, run_id: str) -> SimulationResult | None:
        run = await self.get_run(run_id)
        if not run or not run.result_json:
            return None
        return SimulationResult.model_validate_json(run.result_json)

    async def get_input(self, run_id: str) -> SimulationInput | None:
        run = await self.get_run(run_id)
        if not run:
            return None
        return SimulationInput.model_validate_json(run.input_json)

    async def save_checkpoint(
        self,
        run_id: str,
        period: int,
        agents: list[AgentState],
        world: WorldState,
    ) -> None:
        checkpoint_dir = self.settings.logs_path / run_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "period": period,
            "agents": [a.model_dump() for a in agents],
            "world": world.model_dump(),
        }
        path = checkpoint_dir / f"checkpoint_p{period:04d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_latest_checkpoint_agents(self, run_id: str) -> list[AgentState] | None:
        checkpoint_dir = self.settings.logs_path / run_id
        if not checkpoint_dir.exists():
            return None
        files = sorted(checkpoint_dir.glob("checkpoint_p*.json"))
        if not files:
            return None
        payload = json.loads(files[-1].read_text(encoding="utf-8"))
        agents_raw = payload.get("agents", [])
        if not agents_raw:
            return None
        return [AgentState.model_validate(a) for a in agents_raw]

    @staticmethod
    def _rank_map_for_agents(result: SimulationResult | None, agents: list[AgentState]) -> dict[str, int]:
        rank_by_id: dict[str, int] = {}
        if result and result.top_agents:
            for rank, score in enumerate(result.top_agents, start=1):
                rank_by_id[score.agent_id] = rank
        next_rank = len(rank_by_id) + 1
        for agent in sorted(agents, key=lambda item: item.agent_id):
            if agent.agent_id not in rank_by_id:
                rank_by_id[agent.agent_id] = next_rank
                next_rank += 1
        return rank_by_id

    @staticmethod
    def _max_agents_in_comparisons(comparisons) -> int:
        if not comparisons:
            return 0
        if isinstance(comparisons[0], dict):
            return max(len(item.get("agents", [])) for item in comparisons)
        return max(len(item.agents) for item in comparisons)

    async def _build_paths_from_agents(
        self,
        run_id: str,
        agents: list[AgentState],
        result: SimulationResult,
        limit: int,
    ) -> list[AgentDecisionPath]:
        if result.top_agents:
            top_scores = result.top_agents[:limit]
        else:
            sim_input = await self.get_input(run_id)
            if not sim_input:
                return []
            top_scores = rank_agents(
                agents,
                sim_input.goal,
                sim_input.current_state.resources,
                top_n=limit,
            )
        return build_agent_decision_paths(agents, top_scores, limit=limit)

    async def list_agent_decisions(self, run_id: str, limit: int = 20) -> dict:
        result = await self.get_result(run_id)
        if not result:
            return {"paths": [], "period_comparisons": [], "time_config": time_config_dict()}

        time_cfg = await self._time_config_for_run(run_id, result)
        tc = time_cfg

        checkpoint_agents = self.load_latest_checkpoint_agents(run_id)
        if checkpoint_agents:
            rank_by_id = self._rank_map_for_agents(result, checkpoint_agents)
            comparisons = build_period_comparisons_from_agents(
                checkpoint_agents,
                rank_by_id,
                unit=tc["period_time_unit"],
                length=tc["period_time_length"],
                start_date=tc["simulation_start_date"],
            )
            if self._max_agents_in_comparisons(comparisons) > 0:
                paths = await self._build_paths_from_agents(run_id, checkpoint_agents, result, limit)
                return {
                    "paths": [p.model_dump() for p in paths],
                    "period_comparisons": [c.model_dump() for c in comparisons],
                    "time_config": time_cfg,
                }

        if result.period_comparisons and self._max_agents_in_comparisons(result.period_comparisons) > 1:
            paths = result.agent_paths[:limit]
            comparisons = self._ensure_period_labels(result.period_comparisons, tc)
            return {
                "paths": [p.model_dump() for p in paths],
                "period_comparisons": [c.model_dump() for c in comparisons],
                "time_config": time_cfg,
            }

        paths = result.agent_paths[:limit]
        if paths and self._max_agents_in_comparisons(build_period_comparisons(paths, **self._tc_kwargs(tc))) > 1:
            comparisons = build_period_comparisons(paths, **self._tc_kwargs(tc))
            return {
                "paths": [p.model_dump() for p in paths],
                "period_comparisons": [c.model_dump() for c in comparisons],
                "time_config": time_cfg,
            }

        # Fallback for older runs: champion only
        if result.champion_timeline:
            steps = [
                {
                    "period": t.period,
                    "world_summary": t.world_state.narrative_summary or "",
                    "events": [e.event_type for e in t.world_state.recent_events],
                    "event_summaries": [
                        {
                            "event_type": e.event_type,
                            "description": e.description or e.event_type,
                            "impact": e.impact,
                        }
                        for e in t.world_state.recent_events
                    ],
                    "action": t.action.value if hasattr(t.action, "value") else t.action,
                    "decision": t.decision,
                    "reasoning": t.agent_thought,
                    "outcome": t.result.narrative if t.result else "",
                    "success": t.result.success if t.result else True,
                }
                for t in result.champion_timeline
            ]
            fallback_paths = [
                {
                    "agent_id": result.champion_agent_id,
                    "rank": 1,
                    "total_score": result.top_agents[0].total_score if result.top_agents else 0,
                    "eliminated": False,
                    "steps": steps,
                }
            ]
            comparisons = build_period_comparisons(
                [AgentDecisionPath.model_validate(p) for p in fallback_paths],
                **self._tc_kwargs(tc),
            )
            for comp, step in zip(comparisons, steps):
                comp.event_summaries = [
                    EventSummary.model_validate(e) for e in step.get("event_summaries", [])
                ]
            return {
                "paths": fallback_paths,
                "period_comparisons": [c.model_dump() for c in comparisons],
                "time_config": time_cfg,
            }
        return {"paths": [], "period_comparisons": [], "time_config": time_cfg}

    @staticmethod
    def _tc_kwargs(time_cfg: dict) -> dict:
        return {
            "unit": time_cfg["period_time_unit"],
            "length": time_cfg["period_time_length"],
            "start_date": time_cfg["simulation_start_date"],
        }

    @staticmethod
    def _ensure_period_labels(comparisons, time_cfg: dict):
        updated = []
        for comp in comparisons:
            if comp.period_label:
                updated.append(comp)
                continue
            data = comp.model_dump()
            data["period_label"] = compute_period_label(
                comp.period,
                unit=time_cfg["period_time_unit"],
                length=time_cfg["period_time_length"],
                start_date=time_cfg["simulation_start_date"],
            )
            from prds.models.domain import PeriodComparison as PC

            updated.append(PC.model_validate(data))
        return updated

    async def list_agents_from_result(self, run_id: str, offset: int = 0, limit: int = 50) -> list[dict]:
        result = await self.get_result(run_id)
        if not result:
            return []
        agents_data = []
        for score in result.top_agents[offset : offset + limit]:
            path = next((p for p in result.agent_paths if p.agent_id == score.agent_id), None)
            agents_data.append(
                {
                    "agent_id": score.agent_id,
                    "total_score": score.total_score,
                    "goal_achievement": score.goal_achievement,
                    "final_resources": score.final_resources.model_dump(),
                    "decision_count": len(path.steps) if path else 0,
                    "last_action": path.steps[-1].action.value if path and path.steps else None,
                }
            )
        return agents_data
