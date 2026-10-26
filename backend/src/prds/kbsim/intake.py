"""Silent intake: turn a bare goal + knowledge base into a simulatable brief.

This replaces the old interactive refine modal. The user only types a goal; the
structuring happens server-side inside the run, so nothing is asked back.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field, field_validator

from prds.kbsim.prompts import INTAKE_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import CurrentState, MetricSpec, TargetGoal

logger = logging.getLogger(__name__)


class IntakeBrief(BaseModel):
    background: str = Field(..., min_length=1)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    metric_specs: list[MetricSpec] = Field(..., min_length=1)
    notes: str = ""

    @field_validator("metric_specs", mode="before")
    @classmethod
    def require_measured_baselines(cls, values):
        for spec in values:
            if isinstance(spec, dict) and not {"name", "baseline", "target"} <= spec.keys():
                raise ValueError("Every metric requires a name, baseline, and target")
        return values


async def build_intake_brief(
    llm: LLMClient,
    *,
    goal: TargetGoal,
    current_state: CurrentState,
    kb_context: str,
) -> IntakeBrief:
    payload = {
        "final_goal": goal.description,
        "user_provided_background": current_state.background or "(未提供，请从知识库推断)",
        "user_provided_constraints": list(current_state.constraints),
        "declared_success_metrics": goal.success_metrics or {},
        "knowledge_base_retrieval": kb_context[:8000] or "(知识库为空)",
    }
    user = (
        "把下面的输入整理成可推演的结构化简报，并从知识库中读出可量化指标。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    brief = await llm.structured_complete(
        INTAKE_SYSTEM, user, IntakeBrief, model=llm.analysis_model
    )
    if not brief.background.strip() or not brief.metric_specs:
        raise ValueError("Intake requires background and measurable metrics")
    if len({spec.name.strip() for spec in brief.metric_specs}) != len(brief.metric_specs):
        raise ValueError("Metric names must be unique")
    if any(not spec.name.strip() for spec in brief.metric_specs):
        raise ValueError("Metric name required")

    logger.info(
        "Intake brief ready: %d metrics, %d constraints, %d risks",
        len(brief.metric_specs),
        len(brief.constraints),
        len(brief.risks),
    )
    return brief
