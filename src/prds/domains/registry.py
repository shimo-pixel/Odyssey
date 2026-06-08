from dataclasses import dataclass
from typing import Any, Callable

from prds.models.domain import (
    ActionResult,
    AgentState,
    GoalStatus,
    ResourceSnapshot,
    TargetGoal,
    WorldState,
)


@dataclass(frozen=True)
class DomainProfile:
    id: str
    label: str
    description: str
    default_resources: dict[str, Any]
    default_success_metrics: dict[str, float]
    default_market_info: dict[str, Any]
    execute_action: Callable[..., ActionResult]
    compute_goal_status: Callable[[ResourceSnapshot, TargetGoal], GoalStatus]
    should_eliminate: Callable[[AgentState, TargetGoal, WorldState], tuple[bool, str | None]]
    build_decision_context: Callable[[AgentState, WorldState, TargetGoal], dict]
    score_resource_efficiency: Callable[[AgentState, ResourceSnapshot], float]
    build_system_prompt: Callable[[str], str]


def _load_profiles() -> dict[str, DomainProfile]:
    from prds.domains import startup

    return {
        startup.PROFILE.id: startup.PROFILE,
    }


_PROFILES = _load_profiles()


def get_domain_profile(domain_id: str) -> DomainProfile:
    profile = _PROFILES.get(domain_id)
    if profile is None:
        return _PROFILES["startup"]
    return profile


def list_domain_profiles() -> list[dict[str, str]]:
    return [
        {"id": p.id, "label": p.label, "description": p.description}
        for p in _PROFILES.values()
    ]
