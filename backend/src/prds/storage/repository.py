import json
import shutil
import uuid
from datetime import datetime, timezone

from sqlalchemy import inspect, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from prds.config import Settings, get_settings
from prds.models.domain import (
    BranchStateUpdate,
    ModelInfo,
    SimulationIssue,
    SimulationInput,
    SimulationPhase,
    SimulationProgress,
    SimulationResult,
    SimulationStatus,
)
from prds.simulation.control import get_control
from prds.storage.models import Base, ChatMessage, ChatSession, SimulationRun


def _migrate_simulation_runs(sync_conn) -> None:
    """Lightweight SQLite migrations for event-driven schema renames."""
    insp = inspect(sync_conn)
    if "simulation_runs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("simulation_runs")}

    if "current_event_index" not in cols:
        if "current_period" in cols:
            sync_conn.execute(
                text("ALTER TABLE simulation_runs RENAME COLUMN current_period TO current_event_index")
            )
        else:
            sync_conn.execute(
                text(
                    "ALTER TABLE simulation_runs ADD COLUMN current_event_index INTEGER NOT NULL DEFAULT 0"
                )
            )

    if "total_events" not in cols:
        if "total_periods" in cols:
            sync_conn.execute(
                text("ALTER TABLE simulation_runs RENAME COLUMN total_periods TO total_events")
            )
        else:
            sync_conn.execute(
                text("ALTER TABLE simulation_runs ADD COLUMN total_events INTEGER NOT NULL DEFAULT 0")
            )

    for name, definition in {
        "model_info_json": "TEXT",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
        "failure_json": "TEXT",
    }.items():
        if name not in cols:
            sync_conn.execute(text(f"ALTER TABLE simulation_runs ADD COLUMN {name} {definition}"))


def _migrate_kb_documents(sync_conn) -> None:
    """Add category_id / storage_path to kb_documents when upgrading existing DBs."""
    insp = inspect(sync_conn)
    if "kb_documents" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("kb_documents")}
    if "category_id" not in cols:
        sync_conn.execute(
            text(
                "ALTER TABLE kb_documents ADD COLUMN category_id VARCHAR(64) NOT NULL DEFAULT ''"
            )
        )
    if "storage_path" not in cols:
        sync_conn.execute(
            text("ALTER TABLE kb_documents ADD COLUMN storage_path VARCHAR(1024)")
        )


def _migrate_kb_categories(sync_conn) -> None:
    """Add description to kb_categories when upgrading existing DBs."""
    insp = inspect(sync_conn)
    if "kb_categories" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("kb_categories")}
    if "description" not in cols:
        sync_conn.execute(
            text("ALTER TABLE kb_categories ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        )


class SimulationRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_async_engine(self.settings.prds_database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_migrate_simulation_runs)
            await conn.run_sync(_migrate_kb_documents)
            await conn.run_sync(_migrate_kb_categories)

    async def create_run(self, simulation_input: SimulationInput, model_info: ModelInfo | None = None) -> str:
        run_id = str(uuid.uuid4())
        config = simulation_input.config
        async with self.session_factory() as session:
            run = SimulationRun(
                id=run_id,
                status=SimulationStatus.PENDING.value,
                phase=SimulationPhase.PENDING.value,
                total_events=config.max_events,
                total_agents=config.agent_count,
                alive_agents=config.agent_count,
                input_json=simulation_input.model_dump_json(),
                model_info_json=model_info.model_dump_json() if model_info else None,
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
        current_event_index: int | None = None,
        alive_agents: int | None = None,
        progress_pct: float | None = None,
        error: str | None = None,
        warnings: list[SimulationIssue] | None = None,
        failure: SimulationIssue | None = None,
        total_events: int | None = None,
    ) -> None:
        async with self.session_factory() as session:
            run = await session.get(SimulationRun, run_id)
            if not run:
                return
            if run.status in ("cancelled", "interrupted", "completed", "failed"):
                return
            if total_events is not None:
                run.total_events = total_events
            if warnings is not None:
                run.warnings_json = json.dumps([w.model_dump() for w in warnings])
            if failure:
                run.failure_json = failure.model_dump_json()
            if status:
                run.status = status.value
            if phase:
                run.phase = phase.value
            if current_event_index is not None:
                run.current_event_index = current_event_index
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
            if run.status in ("cancelled", "interrupted", "failed"):
                return
            result.model_info = ModelInfo.model_validate_json(run.model_info_json) if run.model_info_json else None
            run.warnings_json = json.dumps([w.model_dump() for w in result.warnings])
            run.result_json = result.model_dump_json()
            run.status = SimulationStatus.COMPLETED.value
            run.phase = SimulationPhase.COMPLETED.value
            run.progress_pct = 100.0
            run.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def interrupt_active_runs(self) -> None:
        async with self.session_factory() as session:
            await session.execute(update(SimulationRun).where(
                SimulationRun.status.in_(["pending", "running", "paused"])
            ).values(status="interrupted", error="Service interrupted; run again to continue.",
                     updated_at=datetime.now(timezone.utc)))
            await session.commit()

    async def list_runs(self, limit: int = 50) -> list[SimulationRun]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SimulationRun)
                .order_by(SimulationRun.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_run(self, run_id: str) -> SimulationRun | None:
        async with self.session_factory() as session:
            return await session.get(SimulationRun, run_id)

    async def delete_run(self, run_id: str) -> bool:
        async with self.session_factory() as session:
            run = await session.get(SimulationRun, run_id)
            if not run:
                return False
            await session.delete(run)
            await session.commit()

        checkpoint_dir = self.settings.logs_path / run_id
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir, ignore_errors=True)

        get_control().cleanup(run_id)
        return True

    async def _time_config_for_run(self, run_id: str, result: SimulationResult | None) -> dict:
        return {}

    async def get_progress(self, run_id: str) -> SimulationProgress | None:
        run = await self.get_run(run_id)
        if not run:
            return None
        control = get_control()
        return SimulationProgress(
            simulation_id=run.id,
            status=SimulationStatus(run.status),
            phase=SimulationPhase(run.phase),
            current_event_index=run.current_event_index,
            total_events=run.total_events,
            alive_agents=run.alive_agents,
            total_agents=run.total_agents,
            progress_pct=run.progress_pct,
            error=run.error,
            model_info=ModelInfo.model_validate_json(run.model_info_json) if run.model_info_json else None,
            warnings=[SimulationIssue.model_validate(w) for w in json.loads(run.warnings_json or "[]")],
            failure=SimulationIssue.model_validate_json(run.failure_json) if run.failure_json else None,
            can_pause=(run.status == "running" and run.phase == "branch_sim" and control.can_pause(run_id)),
            pause_pending=control.is_pause_requested(run_id),
            pending_user_events=control.pending_event_count(run_id),
        )

    async def get_result(self, run_id: str) -> SimulationResult | None:
        run = await self.get_run(run_id)
        if not run or not run.result_json:
            return None
        result = SimulationResult.model_validate_json(run.result_json)
        sim_input = await self.get_input(run_id)
        if sim_input and sim_input.config.domain_id:
            result = result.model_copy(update={"domain_id": sim_input.config.domain_id})
        return result

    async def get_input(self, run_id: str) -> SimulationInput | None:
        run = await self.get_run(run_id)
        if not run:
            return None
        return SimulationInput.model_validate_json(run.input_json)

    async def save_checkpoint(
        self,
        run_id: str,
        event_index: int,
        states: list[BranchStateUpdate],
    ) -> None:
        """Persist a diagnostic snapshot; this is not a resumable checkpoint."""
        checkpoint_dir = self.settings.logs_path / run_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "event_index": event_index,
            "branches": [s.model_dump() for s in states],
        }
        path = checkpoint_dir / f"checkpoint_e{event_index:04d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def list_agent_decisions(self, run_id: str, limit: int = 20) -> dict:
        result = await self.get_result(run_id)
        if not result:
            return {"paths": [], "event_comparisons": [], "domain_id": "startup"}
        return {
            "paths": [p.model_dump() for p in result.agent_paths[:limit]],
            "event_comparisons": [c.model_dump() for c in result.event_comparisons],
            "domain_id": result.domain_id,
        }

    async def list_agents_from_result(self, run_id: str, offset: int = 0, limit: int = 50) -> list[dict]:
        result = await self.get_result(run_id)
        if not result:
            return []
        paths_by_id = {p.agent_id: p for p in result.agent_paths}
        agents_data = []
        for branch in result.branches[offset : offset + limit]:
            path = paths_by_id.get(branch.branch_id)
            agents_data.append(
                {
                    "agent_id": branch.branch_id,
                    "label": branch.label,
                    "rationality": branch.rationality.value,
                    "rank": branch.rank,
                    "total_score": branch.final_progress,
                    "goal_achievement": branch.final_progress,
                    "final_metrics": branch.final_metrics,
                    "decision_count": len(path.steps) if path else 0,
                    "last_action": path.steps[-1].action if path and path.steps else None,
                }
            )
        return agents_data

    async def list_chat_sessions(self, limit: int = 50) -> list[ChatSession]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ChatSession)
                .order_by(ChatSession.updated_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_chat_session(self, session_id: str) -> ChatSession | None:
        async with self.session_factory() as session:
            return await session.get(ChatSession, session_id)

    async def list_chat_messages(self, session_id: str) -> list[ChatMessage]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
            )
            return list(result.scalars().all())

    async def create_chat_session(self, *, title: str = "", model_id: str | None = None) -> ChatSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = ChatSession(
            id=session_id,
            title=(title or "").strip()[:256],
            model_id=model_id or None,
            created_at=now,
            updated_at=now,
        )
        async with self.session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def append_chat_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        model: str | None = None,
    ) -> ChatMessage | None:
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            chat = await session.get(ChatSession, session_id)
            if not chat:
                return None
            msg = ChatMessage(
                id=msg_id,
                session_id=session_id,
                role=role,
                content=content,
                model=model,
                created_at=now,
            )
            session.add(msg)
            chat.updated_at = now
            if role == "user" and not (chat.title or "").strip():
                chat.title = content.strip()[:256]
            await session.commit()
            await session.refresh(msg)
        return msg

    async def delete_chat_session(self, session_id: str) -> bool:
        async with self.session_factory() as session:
            chat = await session.get(ChatSession, session_id)
            if not chat:
                return False
            msgs = await session.execute(
                select(ChatMessage).where(ChatMessage.session_id == session_id)
            )
            for msg in msgs.scalars().all():
                await session.delete(msg)
            await session.delete(chat)
            await session.commit()
        return True
