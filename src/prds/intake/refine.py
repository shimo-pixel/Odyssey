"""Step ①: take the user's raw situation/goal/constraints and use an LLM to
expand, clarify, and structure them into a richer proposal that the user can
review and edit before the simulation runs.

The output deliberately separates what the user said from what the model
*inferred* (assumptions), so the user can correct hallucinated context before
it propagates into the research report, knowledge graph, and agents.
"""

import json
import logging

from pydantic import BaseModel, Field

from prds.llm.client import LLMClient

logger = logging.getLogger(__name__)


class RefineRequest(BaseModel):
    background: str = Field(description="User's current-situation description")
    goal: str = Field(description="User's final goal description")
    constraints: list[str] = Field(default_factory=list)
    domain_id: str = "startup"


class RefinedProposal(BaseModel):
    background: str = Field(description="Expanded, clarified current situation")
    goal: str = Field(description="Sharpened goal with measurable framing")
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    success_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="1-3 measurable targets mapped to simulation resource fields",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Context the model inferred/added that the user should verify",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Gaps the user may want to fill for a better simulation",
    )
    notes: str = Field(default="", description="Short summary of what was expanded")


REFINE_SYSTEM = """You are an intake analyst for a decision-simulation system.
The user gives a rough description of their current situation, their final goal,
and optional constraints. Your job is to expand and structure it into a clearer,
more concrete brief WITHOUT inventing facts that contradict the user.

Principles:
- Keep the user's original language (if they wrote Chinese, respond in Chinese).
- Expand vague statements into concrete, domain-grounded detail, but mark anything
  you inferred (not stated by the user) in `assumptions` so they can correct it.
- The goal should be measurable and time-bound where possible.
- Constraints should be concrete and testable (budget caps, time, headcount, legal).
- risks/opportunities: realistic, domain-specific, 3-6 each.
- open_questions: 2-4 specific things that, if answered, would materially improve realism.
- success_metrics: derive 1-3 measurable targets from the user's goal ONLY. Use these keys
  when relevant (omit irrelevant SaaS defaults like users:100000 unless the goal is about users):
  cash, revenue, users, product_maturity, brand_awareness, market_share.
  Example: "回本5万再赚5万" with starting cash ~50 -> {"cash": 100}.
  Example: "月营收10万" -> {"revenue": 10} (same units as the scenario).
- Do NOT be over-optimistic. Surface real headwinds.
- `notes`: one or two sentences in the user's language describing what you expanded.
Return valid JSON only."""


def _build_user_payload(req: RefineRequest) -> str:
    payload = {
        "domain_id": req.domain_id,
        "current_situation": req.background,
        "final_goal": req.goal,
        "constraints": req.constraints,
    }
    return (
        "Expand and structure the following user input into a reviewable brief. "
        "Mark inferred context as assumptions.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


async def refine_user_input(llm: LLMClient, req: RefineRequest) -> RefinedProposal:
    proposal = await llm.structured_complete(
        REFINE_SYSTEM,
        _build_user_payload(req),
        RefinedProposal,
        model=llm.analysis_model,
    )
    if not proposal.background.strip():
        proposal.background = req.background
    if not proposal.goal.strip():
        proposal.goal = req.goal
    if not proposal.constraints:
        proposal.constraints = list(req.constraints)
    logger.info(
        "Refined intake: +%d risks, +%d opportunities, +%d assumptions",
        len(proposal.risks),
        len(proposal.opportunities),
        len(proposal.assumptions),
    )
    return proposal
