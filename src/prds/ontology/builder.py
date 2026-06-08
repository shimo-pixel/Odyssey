import json
import re
from typing import Any

from prds.llm.client import LLMClient
from prds.models.domain import (
    CurrentState,
    OntologyGraph,
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
) -> OntologyGraph:
    user_content = json.dumps(
        {
            "current_state": current_state.model_dump(),
            "goal": goal.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )

    response = await llm.complete(
        system=ONTOLOGY_SYSTEM_PROMPT,
        user=user_content,
        model=llm.analysis_model,
    )
    data = _parse_json_response(response)
    return OntologyGraph.model_validate(data)
