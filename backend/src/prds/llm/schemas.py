import json

from pydantic import BaseModel, Field

from prds.models.domain import AgentDecision, CounterfactualComparison, EventCategory


class CounterfactualBatch(BaseModel):
    comparisons: list[CounterfactualComparison] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    principles: list[str] = Field(default_factory=list)
    key_turning_points: list[str] = Field(default_factory=list)
    success_factors: list[str] = Field(default_factory=list)
    failure_avoidance_factors: list[str] = Field(default_factory=list)
    recommended_roadmap: list[str] = Field(default_factory=list)


class StepOutcomeAnalysis(BaseModel):
    analysis: str = Field(
        min_length=1,
        max_length=800,
        description="Macro strategic interpretation of this step — no specific financial figures",
    )


class PlannedEventDraft(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    category: EventCategory
    impact: float = Field(ge=-1.0, le=1.0)
    severity: float = Field(default=0.6, ge=0.1, le=1.0)
    probability: float = Field(default=0.7, ge=0.0, le=1.0)
    description: str = Field(min_length=1, max_length=500)
    rationale: str = Field(
        default="",
        max_length=300,
        description="Why this event is likely at this point in the sequence per the industry report",
    )


class EventPlan(BaseModel):
    narrative_arc: str = ""
    events: list[PlannedEventDraft] = Field(default_factory=list)


__all__ = [
    "AgentDecision",
    "CounterfactualBatch",
    "CounterfactualComparison",
    "EventPlan",
    "PlannedEventDraft",
    "StepOutcomeAnalysis",
    "SynthesisOutput",
]
