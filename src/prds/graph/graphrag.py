import asyncio
import json
import logging
import re
from typing import Any

from prds.graph.neo4j_store import Neo4jGraphStore, get_neo4j_store
from prds.llm.client import LLMClient
from prds.models.domain import (
    BackgroundReport,
    CurrentState,
    KnowledgeGraphData,
    OntologyEntity,
    OntologyGraph,
    OntologyRelation,
    TargetGoal,
    WorldBackground,
)
from prds.ontology.builder import _parse_json_response, build_ontology
from prds.ontology.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

CHUNK_EXTRACT_PROMPT = """You are a GraphRAG entity extraction engine.
From the given text chunk, extract entities and relationships for a knowledge graph.
Return JSON only:
{
  "entities": [
    {"name": "...", "entity_type": "organization|person|product|capital|market|technology|time", "description": "..."}
  ],
  "relationships": [
    {"source": "entity name", "target": "entity name", "relation_type": "owns|influences|depends_on|cooperates|competes|consumes|grows|constrains", "description": "..."}
  ]
}
Extract concrete entities from the user's situation. Use the same language as the input."""

WORLD_SUMMARY_PROMPT = """You are a GraphRAG community summarizer for a decision simulation world model.
Given entities, relations, risks, opportunities and user context, write:
1) A 2-3 paragraph world background that will drive future random events in the simulation.
2) Three short community summaries: market dynamics, organizational context, resource constraints.
Return JSON:
{
  "summary": "...",
  "community_summaries": ["...", "...", "..."]
}"""


def compose_document(
    current_state: CurrentState,
    goal: TargetGoal,
    report: BackgroundReport | None = None,
) -> str:
    """Public alias: assemble the seed document fed to GraphRAG / Graphiti."""
    return _compose_document(current_state, goal, report)


def _compose_document(
    current_state: CurrentState,
    goal: TargetGoal,
    report: BackgroundReport | None = None,
) -> str:
    parts = [
        f"## 当前现状\n{current_state.background}",
        f"## 最终目标\n{goal.description}",
    ]
    if current_state.constraints:
        parts.append("## 约束\n" + "\n".join(f"- {c}" for c in current_state.constraints))
    if current_state.risks:
        parts.append("## 风险\n" + "\n".join(f"- {r}" for r in current_state.risks))
    if current_state.opportunities:
        parts.append("## 机会\n" + "\n".join(f"- {o}" for o in current_state.opportunities))
    if report and report.report.strip():
        parts.append("## 行业背景研究报告\n" + report.report.strip())
    return "\n\n".join(parts)


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return [text[:max_chars]] if text else [""]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            current = para if len(para) <= max_chars else para[:max_chars]
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def _slug_id(name: str, index: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", name.strip().lower())[:40]
    return f"e_{index}_{slug or 'entity'}"


def _merge_extractions(
    chunk_results: list[dict[str, Any]],
    current_state: CurrentState,
    goal: TargetGoal,
) -> OntologyGraph:
    name_to_id: dict[str, str] = {}
    entities: list[OntologyEntity] = []
    relations: list[OntologyRelation] = []
    idx = 0

    def ensure_entity(name: str, entity_type: str, description: str = "") -> str:
        nonlocal idx
        key = name.strip().lower()
        if not key:
            return ""
        if key in name_to_id:
            return name_to_id[key]
        idx += 1
        eid = _slug_id(name, idx)
        name_to_id[key] = eid
        entities.append(
            OntologyEntity(
                id=eid,
                entity_type=entity_type or "entity",
                name=name.strip(),
                properties={"description": description} if description else {},
            )
        )
        return eid

    for chunk in chunk_results:
        for raw in chunk.get("entities", []):
            ensure_entity(
                raw.get("name", "Unknown"),
                raw.get("entity_type", "entity"),
                raw.get("description", ""),
            )
        for raw in chunk.get("relationships", []):
            src = ensure_entity(raw.get("source", ""), "entity", "")
            tgt = ensure_entity(raw.get("target", ""), "entity", "")
            if src and tgt:
                relations.append(
                    OntologyRelation(
                        source_id=src,
                        target_id=tgt,
                        relation_type=raw.get("relation_type", "influences"),
                    )
                )

    if len(entities) < 3:
        raise ValueError("GraphRAG extraction produced fewer than 3 entities")

    return OntologyGraph(
        entities=entities,
        relations=relations,
        risks=current_state.risks or [],
        opportunities=current_state.opportunities or [],
        constraints=current_state.constraints or [],
        targets=[goal.description],
    )


class GraphRAGIndexer:
    """GraphRAG-style indexing: chunk → extract → merge → summarize → graph."""

    def __init__(
        self,
        llm: LLMClient,
        neo4j: Neo4jGraphStore | None = None,
        *,
        use_graphrag: bool = True,
    ) -> None:
        self.llm = llm
        self.neo4j = neo4j or get_neo4j_store()
        self.use_graphrag = use_graphrag

    async def _extract_chunk(self, chunk: str) -> dict[str, Any]:
        response = await self.llm.complete(
            system=CHUNK_EXTRACT_PROMPT,
            user=chunk,
            model=self.llm.analysis_model,
        )
        return _parse_json_response(response)

    async def _summarize_world(
        self,
        ontology: OntologyGraph,
        document: str,
    ) -> tuple[str, list[str], dict[str, str]]:
        entity_reports = {
            e.id: (e.properties.get("description") or e.name) if e.properties else e.name
            for e in ontology.entities
        }

        payload = {
            "entities": [e.model_dump() for e in ontology.entities[:20]],
            "relations": [r.model_dump() for r in ontology.relations[:30]],
            "risks": ontology.risks,
            "opportunities": ontology.opportunities,
            "constraints": ontology.constraints,
            "user_context_excerpt": document[:2000],
        }
        try:
            response = await self.llm.complete(
                system=WORLD_SUMMARY_PROMPT,
                user=json.dumps(payload, ensure_ascii=False, indent=2),
                model=self.llm.analysis_model,
            )
            data = _parse_json_response(response)
            summary = data.get("summary", "")
            communities = data.get("community_summaries", [])
            if not summary:
                raise ValueError("GraphRAG world summary returned empty summary")
            return summary, communities, entity_reports
        except Exception as exc:
            logger.warning("GraphRAG world summary failed: %s", exc)
            raise

    async def index(
        self,
        simulation_id: str,
        current_state: CurrentState,
        goal: TargetGoal,
        *,
        report: BackgroundReport | None = None,
    ) -> tuple[OntologyGraph, KnowledgeGraphData, WorldBackground]:
        document = _compose_document(current_state, goal, report)

        if not self.use_graphrag:
            ontology = await build_ontology(self.llm, current_state, goal)
            graph_source = "ontology"
        else:
            chunks = _chunk_text(document)
            chunk_results = await asyncio.gather(*[self._extract_chunk(c) for c in chunks])
            ontology = _merge_extractions(list(chunk_results), current_state, goal)
            graph_source = "graphrag"

        kg = KnowledgeGraph()
        kg.build_from_ontology(ontology)
        kg_data = kg.to_data()

        summary, communities, entity_reports = await self._summarize_world(ontology, document)
        background = WorldBackground(
            summary=summary,
            community_summaries=communities,
            entity_reports=entity_reports,
            risks=list(ontology.risks),
            opportunities=list(ontology.opportunities),
            graph_source=graph_source,
            neo4j_persisted=False,
            research_provider=report.provider if report else "off",
            research_report=report.report if report else "",
            research_citations=list(report.citations) if report else [],
        )

        if self.neo4j.available:
            persisted = await self.neo4j.save_simulation_graph(simulation_id, kg_data, background)
            background.neo4j_persisted = persisted

        return ontology, kg_data, background
