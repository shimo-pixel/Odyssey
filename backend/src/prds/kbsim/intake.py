"""Silent intake: turn a bare goal + knowledge base into a simulatable brief.

This replaces the old interactive refine modal. The user only types a goal; the
structuring happens server-side inside the run, so nothing is asked back.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from prds.kbsim.prompts import INTAKE_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import CurrentState, MetricSpec, TargetGoal

logger = logging.getLogger(__name__)


class IntakeBrief(BaseModel):
    background: str = ""
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    metric_specs: list[MetricSpec] = Field(default_factory=list)
    notes: str = ""


def _fallback_metric_specs(goal: TargetGoal) -> list[MetricSpec]:
    """Derive metrics from explicit success_metrics, or fall back to a generic one."""
    specs = [
        MetricSpec(name=name, baseline=0.0, target=float(target))
        for name, target in (goal.success_metrics or {}).items()
        if isinstance(target, (int, float))
    ]
    if specs:
        return specs
    return [MetricSpec(name="目标达成度", unit="%", baseline=0.0, target=100.0)]


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

    try:
        brief = await llm.structured_complete(
            INTAKE_SYSTEM, user, IntakeBrief, model=llm.analysis_model
        )
    except Exception as exc:
        logger.warning("Intake structuring failed, falling back to raw input: %s", exc)
        brief = IntakeBrief(
            background=current_state.background,
            constraints=list(current_state.constraints),
            risks=list(current_state.risks),
            opportunities=list(current_state.opportunities),
        )

    if not brief.background.strip():
        brief.background = current_state.background
    if not brief.constraints:
        brief.constraints = list(current_state.constraints)
    brief.metric_specs = [
        spec for spec in brief.metric_specs if spec.name and spec.name.strip()
    ]
    if not brief.metric_specs:
        brief.metric_specs = _fallback_metric_specs(goal)

    logger.info(
        "Intake brief ready: %d metrics, %d constraints, %d risks",
        len(brief.metric_specs),
        len(brief.constraints),
        len(brief.risks),
    )
    return brief
