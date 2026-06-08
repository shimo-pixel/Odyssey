import random
import uuid
from typing import Sequence

from prds.models.domain import Event, EventCategory, WorldState

EVENT_TEMPLATES: dict[EventCategory, list[tuple[str, float]]] = {
    EventCategory.MACRO: [
        ("economic_downturn", -0.4),
        ("economic_boom", 0.3),
        ("policy_support", 0.35),
        ("policy_restriction", -0.3),
        ("industry_disruption", -0.25),
        ("tech_breakthrough", 0.45),
        ("black_swan", -0.6),
    ],
    EventCategory.MARKET: [
        ("user_growth_surge", 0.4),
        ("user_churn_spike", -0.35),
        ("competitor_entry", -0.3),
        ("competitor_exit", 0.25),
        ("viral_brand_moment", 0.5),
        ("market_saturation", -0.2),
    ],
    EventCategory.ORG: [
        ("key_member_departure", -0.35),
        ("successful_hire", 0.25),
        ("internal_conflict", -0.2),
        ("execution_boost", 0.2),
        ("culture_improvement", 0.15),
    ],
    EventCategory.RESOURCE: [
        ("fundraise_success", 0.5),
        ("fundraise_failure", -0.3),
        ("cashflow_crisis", -0.45),
        ("supply_chain_issue", -0.25),
        ("cost_reduction_win", 0.2),
    ],
}


class EventGenerator:
    def __init__(
        self,
        seed: int | None = None,
        *,
        world_background: str = "",
        entity_hints: list[str] | None = None,
        risks: list[str] | None = None,
        opportunities: list[str] | None = None,
        planned_by_period: dict[int, list[Event]] | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._world_background = world_background
        self._entity_hints = entity_hints or []
        self._risks = risks or []
        self._opportunities = opportunities or []
        self._planned_by_period = planned_by_period or {}
        self._use_planned = bool(self._planned_by_period)

    def _contextual_description(
        self,
        event_type: str,
        category: EventCategory,
        severity: float,
        period: int,
    ) -> str:
        base = event_type.replace("_", " ")
        hint = self._rng.choice(self._entity_hints) if self._entity_hints else None
        if category == EventCategory.MARKET and self._opportunities:
            ctx = self._rng.choice(self._opportunities)
            return f"[T{period}] 市场事件「{base}」与背景相关：{ctx[:80]}（严重度 {severity:.2f}）"
        if severity >= 0.5 and self._risks:
            ctx = self._rng.choice(self._risks)
            return f"[T{period}] 风险事件「{base}」：{ctx[:80]}（严重度 {severity:.2f}）"
        if hint:
            return f"[T{period}] 「{base}」影响实体 {hint}（严重度 {severity:.2f}）"
        if self._world_background:
            return f"[T{period}] {base}（GraphRAG 世界背景下发生，严重度 {severity:.2f}）"
        return f"{base.title()} occurred (severity={severity:.2f})"

    def generate_period_events(self, period: int, count: int | None = None) -> list[Event]:
        if count is None:
            count = self._rng.randint(1, 10)

        events: list[Event] = []
        categories = list(EventCategory)
        for _ in range(count):
            category = self._rng.choice(categories)
            event_type, base_impact = self._rng.choice(EVENT_TEMPLATES[category])
            severity = self._rng.uniform(0.2, 1.0)
            probability = self._rng.uniform(0.1, 0.9)
            impact = max(-1.0, min(1.0, base_impact * severity))

            events.append(
                Event(
                    event_id=f"evt_{period}_{uuid.uuid4().hex[:8]}",
                    event_type=event_type,
                    category=category,
                    impact=impact,
                    probability=probability,
                    severity=severity,
                    description=self._contextual_description(event_type, category, severity, period),
                )
            )
        return events

    def events_for_period(self, period: int) -> list[Event]:
        if self._use_planned:
            return list(self._planned_by_period.get(period, []))
        return self.generate_period_events(period)

    def apply_events_to_world(self, world: WorldState, events: Sequence[Event]) -> WorldState:
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

        event_summary = "; ".join(e.event_type for e in events[:5])
        return world.model_copy(
            update={
                "environment": env,
                "external_market": external_market,
                "competition": competition,
                "policy": policy,
                "technology": technology,
                "recent_events": list(events),
                "narrative_summary": f"Period {world.period}: {event_summary}",
            }
        )
