import asyncio
import uuid
from dataclasses import dataclass, field

from prds.models.domain import Event, UserEventInput


@dataclass
class RunControlState:
    pause_requested: bool = False
    paused: bool = False
    can_pause: bool = True
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    user_events: list[UserEventInput] = field(default_factory=list)


class SimulationControlRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunControlState] = {}

    def _state(self, run_id: str) -> RunControlState:
        if run_id not in self._runs:
            self._runs[run_id] = RunControlState()
        return self._runs[run_id]

    def can_pause(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        return state.can_pause if state else False

    def set_can_pause(self, run_id: str, allowed: bool) -> None:
        self._state(run_id).can_pause = allowed

    def request_pause(self, run_id: str) -> None:
        self._state(run_id).pause_requested = True

    def is_pause_requested(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        return bool(state and state.pause_requested)

    def is_paused(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        return bool(state and state.paused)

    def pending_event_count(self, run_id: str) -> int:
        state = self._runs.get(run_id)
        return len(state.user_events) if state else 0

    def add_user_event(self, run_id: str, event: UserEventInput) -> UserEventInput:
        self._state(run_id).user_events.append(event)
        return event

    def list_pending_user_events(self, run_id: str) -> list[UserEventInput]:
        state = self._runs.get(run_id)
        return list(state.user_events) if state else []

    def clear_pending_user_events(self, run_id: str) -> None:
        self._state(run_id).user_events.clear()

    def resume(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if state is None or not state.paused:
            return False
        state.resume_event.set()
        return True

    def pop_user_events(self, run_id: str, event_index: int) -> list[Event]:
        state = self._state(run_id)
        if not state.user_events:
            return []
        events = [self._to_domain(item, event_index) for item in state.user_events]
        state.user_events.clear()
        return events

    async def maybe_pause_after_event(
        self,
        run_id: str,
        on_paused,
        on_resumed,
    ) -> None:
        state = self._state(run_id)
        if not state.pause_requested:
            return
        state.pause_requested = False
        state.paused = True
        state.resume_event.clear()
        await on_paused()
        await state.resume_event.wait()
        state.paused = False
        await on_resumed()

    def cleanup(self, run_id: str) -> None:
        state = self._runs.pop(run_id, None)
        if state:
            state.resume_event.set()

    @staticmethod
    def _to_domain(item: UserEventInput, event_index: int) -> Event:
        return Event(
            event_id=f"user_{event_index}_{uuid.uuid4().hex[:8]}",
            event_type="user_defined",
            category=item.category,
            impact=max(-1.0, min(1.0, item.impact)),
            probability=1.0,
            severity=item.severity,
            description=item.description.strip(),
        )


_registry = SimulationControlRegistry()


def get_control() -> SimulationControlRegistry:
    return _registry
