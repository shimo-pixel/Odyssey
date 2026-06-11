import uuid
from typing import Sequence

from prds.models.domain import Event, EventCategory, WorldState


class EventProcessor:
    """Apply exogenous events to world state."""

    def __init__(
        self,
        *,
        world_background: str = "",
        entity_hints: list[str] | None = None,
        risks: list[str] | None = None,
        opportunities: list[str] | None = None,
    ) -> None:
        self._world_background = world_background
        self._entity_hints = entity_hints or []
        self._risks = risks or []
        self._opportunities = opportunities or []

    def apply_events_to_world(
        self,
        world: WorldState,
        events: Sequence[Event],
        *,
        event_index: int,
    ) -> WorldState:
        env = world.environment.model_copy()
        external_market = dict(world.external_market)
        competition = dict(world.competition)
        policy = dict(world.policy)
        technology = dict(world.technology)

        for event in events:
            delta = event.impact * event.severity
            if event.category == EventCategory.MACRO:
                env.economic_index = max(0.0, min(2.0, env.economic_index + delta * 0.2))
                env.policy_support = max(0.0, min(1.0, env.policy_support + delta * 0.15))
                if "tech" in event.event_type:
                    env.tech_maturity = max(0.0, min(1.0, env.tech_maturity + delta * 0.2))
            elif event.category == EventCategory.MARKET:
                env.user_growth_rate = max(-0.5, min(1.0, env.user_growth_rate + delta * 0.1))
                external_market["demand_index"] = max(
                    0.0, min(1.0, external_market.get("demand_index", 0.6) + delta * 0.15)
                )
                competition["intensity"] = max(
                    0.0, min(1.0, competition.get("intensity", 0.5) - delta * 0.1)
                )
            elif event.category == EventCategory.ORG:
                technology["innovation_pace"] = max(
                    0.0, min(1.0, technology.get("innovation_pace", 0.5) + delta * 0.1)
                )
            elif event.category == EventCategory.RESOURCE:
                external_market["funding_climate"] = max(
                    0.0, min(1.0, external_market.get("funding_climate", 0.5) + delta * 0.2)
                )

        primary = events[0] if events else None
        event_summary = "; ".join(e.event_type for e in events[:5])
        label = primary.event_type if primary else "none"
        return world.model_copy(
            update={
                "event_index": event_index,
                "environment": env,
                "external_market": external_market,
                "competition": competition,
                "policy": policy,
                "technology": technology,
                "recent_events": list(events),
                "narrative_summary": f"Event #{event_index} ({label}): {event_summary}",
            }
        )


def user_event_to_domain(item, event_index: int) -> Event:
    from prds.models.domain import UserEventInput

    assert isinstance(item, UserEventInput)
    return Event(
        event_id=f"user_{event_index}_{uuid.uuid4().hex[:8]}",
        event_type="user_defined",
        category=item.category,
        impact=max(-1.0, min(1.0, item.impact)),
        probability=1.0,
        severity=item.severity,
        description=item.description.strip(),
    )
