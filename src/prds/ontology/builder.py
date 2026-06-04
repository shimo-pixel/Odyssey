import json
import re
from typing import Any

from prds.llm.client import LLMClient
from prds.models.domain import (
    CurrentState,
    OntologyEntity,
    OntologyGraph,
    OntologyRelation,
    TargetGoal,
)


ONTOLOGY_SYSTEM_PROMPT = """You are an ontology extraction engine for a decision simulation system.
Extract structured entities and relations from the user's current state and goal.
Return valid JSON only, matching this schema:
{
  "entities": [{"id": "e1", "entity_type": "organization|person|product|capital|market|technology|time", "name": "...", "properties": {}}],
  "relations": [{"source_id": "e1", "target_id": "e2", "relation_type": "owns|influences|depends_on|cooperates|competes|consumes|grows|constrains"}],
  "risks": ["..."],
  "opportunities": ["..."],
  "constraints": ["..."],
  "targets": ["..."]
}
Extract at least 5 entities and 3 relations when possible."""


def _fallback_ontology(current_state: CurrentState, goal: TargetGoal) -> OntologyGraph:
    """Rule-based fallback when LLM is unavailable."""
    resources = current_state.resources
    entities = [
        OntologyEntity(id="org_main", entity_type="organization", name="Main Organization"),
        OntologyEntity(
            id="product_main",
            entity_type="product",
            name="Core Product",
            properties={"maturity": resources.product_maturity},
        ),
        OntologyEntity(
            id="capital_main",
            entity_type="capital",
            name="Operating Capital",
            properties={"cash": resources.cash},
        ),
        OntologyEntity(id="market_main", entity_type="market", name="Target Market"),
        OntologyEntity(id="goal_target", entity_type="time", name="Goal Deadline"),
    ]
    relations = [
        OntologyRelation(source_id="org_main", target_id="product_main", relation_type="owns"),
        OntologyRelation(source_id="org_main", target_id="capital_main", relation_type="owns"),
        OntologyRelation(source_id="product_main", target_id="market_main", relation_type="depends_on"),
        OntologyRelation(source_id="org_main", target_id="goal_target", relation_type="constrains"),
    ]
    return OntologyGraph(
        entities=entities,
        relations=relations,
        risks=current_state.risks or ["cash burn", "market competition"],
        opportunities=current_state.opportunities or ["market growth"],
        constraints=current_state.constraints or ["limited runway"],
        targets=[goal.description],
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)


async def build_ontology(
    llm: LLMClient,
    current_state: CurrentState,
    goal: TargetGoal,
    *,
    use_llm: bool = True,
) -> OntologyGraph:
    if not use_llm or not llm.api_key_available:
        return _fallback_ontology(current_state, goal)

    user_content = json.dumps(
        {
            "current_state": current_state.model_dump(),
            "goal": goal.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )

    try:
        response = await llm.complete(
            system=ONTOLOGY_SYSTEM_PROMPT,
            user=user_content,
            model=llm.analysis_model,
        )
        data = _parse_json_response(response)
        return OntologyGraph.model_validate(data)
    except Exception:
        return _fallback_ontology(current_state, goal)
