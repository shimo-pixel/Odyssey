import asyncio
import logging
from typing import Any

from prds.config import Settings, get_settings
from prds.models.domain import KnowledgeGraphData, WorldBackground

logger = logging.getLogger(__name__)


class Neo4jGraphStore:
    """Persist simulation knowledge graphs in Neo4j."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._driver = None
        if self.settings.neo4j_enabled:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                )
            except Exception as exc:
                logger.warning("Neo4j driver init failed: %s", exc)
                self._driver = None

    @property
    def available(self) -> bool:
        return self._driver is not None

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def verify(self) -> bool:
        if not self._driver:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j connectivity check failed: %s", exc)
            return False

    def _write_graph(
        self,
        simulation_id: str,
        kg: KnowledgeGraphData,
        background: WorldBackground,
    ) -> None:
        assert self._driver is not None
        with self._driver.session() as session:
            session.run(
                "MATCH (s:Simulation {id: $sim_id}) DETACH DELETE s",
                sim_id=simulation_id,
            )
            session.run(
                """
                MERGE (s:Simulation {id: $sim_id})
                SET s.summary = $summary,
                    s.graph_source = $graph_source,
                    s.community_summaries = $communities
                """,
                sim_id=simulation_id,
                summary=background.summary,
                graph_source=background.graph_source,
                communities=background.community_summaries,
            )
            for node in kg.nodes:
                node_copy = dict(node)
                node_id = node_copy.pop("id")
                entity_type = node_copy.pop("entity_type", "entity")
                name = node_copy.pop("name", node_id)
                description = background.entity_reports.get(node_id, name)
                session.run(
                    """
                    MATCH (s:Simulation {id: $sim_id})
                    MERGE (n:Entity {id: $node_id, simulation_id: $sim_id})
                    SET n.entity_type = $entity_type,
                        n.name = $name,
                        n.description = $description,
                        n += $props
                    MERGE (s)-[:HAS_ENTITY]->(n)
                    """,
                    sim_id=simulation_id,
                    node_id=node_id,
                    entity_type=entity_type,
                    name=name,
                    description=description,
                    props=node_copy,
                )
            for edge in kg.edges:
                edge_copy = dict(edge)
                source = edge_copy.pop("source")
                target = edge_copy.pop("target")
                relation_type = edge_copy.pop("relation_type", "RELATED_TO")
                session.run(
                    """
                    MATCH (a:Entity {id: $source, simulation_id: $sim_id})
                    MATCH (b:Entity {id: $target, simulation_id: $sim_id})
                    MERGE (a)-[r:RELATED {simulation_id: $sim_id, relation_type: $rel}]->(b)
                    SET r += $props
                    """,
                    sim_id=simulation_id,
                    source=source,
                    target=target,
                    rel=relation_type,
                    props=edge_copy,
                )

    def _read_graph(self, simulation_id: str) -> dict[str, Any] | None:
        assert self._driver is not None
        with self._driver.session() as session:
            sim = session.run(
                """
                MATCH (s:Simulation {id: $sim_id})
                RETURN s.summary AS summary, s.graph_source AS graph_source,
                       s.community_summaries AS communities
                """,
                sim_id=simulation_id,
            ).single()
            if not sim:
                return None
            nodes = []
            for record in session.run(
                """
                MATCH (s:Simulation {id: $sim_id})-[:HAS_ENTITY]->(n:Entity)
                RETURN n
                """,
                sim_id=simulation_id,
            ):
                node = record["n"]
                props = dict(node.items())
                nodes.append(props)
            edges = [
                {
                    "source": record["source"],
                    "target": record["target"],
                    "relation_type": record["rel_type"],
                    "first_seen_period": record["first_seen_period"]
                    if record["first_seen_period"] is not None
                    else 0,
                }
                for record in session.run(
                    """
                    MATCH (a:Entity {simulation_id: $sim_id})-[r:RELATED {simulation_id: $sim_id}]->(b:Entity)
                    RETURN a.id AS source, b.id AS target, r.relation_type AS rel_type,
                           r.first_seen_period AS first_seen_period
                    """,
                    sim_id=simulation_id,
                )
            ]
            entity_reports = {
                n.get("id", ""): n.get("description", n.get("name", ""))
                for n in nodes
                if n.get("id")
            }
            return {
                "knowledge_graph": {
                    "nodes": [
                        {
                            "id": n.get("id"),
                            "entity_type": n.get("entity_type", "entity"),
                            "name": n.get("name", n.get("id")),
                            **{
                                k: v
                                for k, v in n.items()
                                if k not in {"id", "entity_type", "name", "simulation_id", "description"}
                            },
                        }
                        for n in nodes
                    ],
                    "edges": edges,
                },
                "world_background": {
                    "summary": sim["summary"] or "",
                    "community_summaries": sim["communities"] or [],
                    "entity_reports": entity_reports,
                    "graph_source": sim["graph_source"] or "neo4j",
                    "neo4j_persisted": True,
                },
            }

    async def save_simulation_graph(
        self,
        simulation_id: str,
        kg: KnowledgeGraphData,
        background: WorldBackground,
    ) -> bool:
        if not self.available:
            return False
        try:
            await asyncio.to_thread(self._write_graph, simulation_id, kg, background)
            return True
        except Exception as exc:
            logger.exception("Neo4j write failed for %s: %s", simulation_id, exc)
            return False

    async def load_simulation_graph(self, simulation_id: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            return await asyncio.to_thread(self._read_graph, simulation_id)
        except Exception as exc:
            logger.exception("Neo4j read failed for %s: %s", simulation_id, exc)
            return None


_store: Neo4jGraphStore | None = None


def get_neo4j_store() -> Neo4jGraphStore:
    global _store
    if _store is None:
        _store = Neo4jGraphStore()
    return _store
