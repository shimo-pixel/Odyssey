import json

from pydantic import BaseModel, Field

from prds.models.domain import AgentDecision, CounterfactualComparison


class CounterfactualBatch(BaseModel):
    comparisons: list[CounterfactualComparison] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    principles: list[str] = Field(default_factory=list)
    key_turning_points: list[str] = Field(default_factory=list)
    success_factors: list[str] = Field(default_factory=list)
    failure_avoidance_factors: list[str] = Field(default_factory=list)
    recommended_roadmap: list[str] = Field(default_factory=list)


__all__ = ["AgentDecision", "CounterfactualBatch", "CounterfactualComparison", "SynthesisOutput"]
