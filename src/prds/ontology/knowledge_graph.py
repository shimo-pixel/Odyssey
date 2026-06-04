import json
from typing import Any

import networkx as nx

from prds.models.domain import (
    KnowledgeGraphData,
    OntologyEntity,
    OntologyGraph,
    OntologyRelation,
)


class KnowledgeGraph:
    """NetworkX-backed knowledge graph for PRDS."""

    NODE_TYPES = {"person", "organization", "product", "capital", "market", "technology", "time"}
    EDGE_TYPES = {
        "owns",
        "influences",
        "depends_on",
        "cooperates",
        "competes",
        "consumes",
        "grows",
        "constrains",
    }

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def add_entity(self, entity: OntologyEntity) -> None:
        self.graph.add_node(
            entity.id,
            entity_type=entity.entity_type,
            name=entity.name,
            **entity.properties,
        )

    def add_relation(self, relation: OntologyRelation) -> None:
        self.graph.add_edge(
            relation.source_id,
            relation.target_id,
            relation_type=relation.relation_type,
        )

    def build_from_ontology(self, ontology: OntologyGraph) -> None:
        for entity in ontology.entities:
            self.add_entity(entity)
        for relation in ontology.relations:
            if relation.source_id in self.graph and relation.target_id in self.graph:
                self.add_relation(relation)

    def to_data(self) -> KnowledgeGraphData:
        nodes = [
            {"id": node_id, **attrs}
            for node_id, attrs in self.graph.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, **attrs}
            for u, v, attrs in self.graph.edges(data=True)
        ]
        return KnowledgeGraphData(nodes=nodes, edges=edges)

    @classmethod
    def from_data(cls, data: KnowledgeGraphData) -> "KnowledgeGraph":
        kg = cls()
        for node in data.nodes:
            node_copy = dict(node)
            node_id = node_copy.pop("id")
            entity_type = node_copy.pop("entity_type", "entity")
            name = node_copy.pop("name", node_id)
            kg.add_entity(
                OntologyEntity(
                    id=node_id,
                    entity_type=entity_type,
                    name=name,
                    properties=node_copy,
                )
            )
        for edge in data.edges:
            edge_copy = dict(edge)
            source = edge_copy.pop("source")
            target = edge_copy.pop("target")
            relation_type = edge_copy.pop("relation_type", "influences")
            kg.add_relation(
                OntologyRelation(
                    source_id=source,
                    target_id=target,
                    relation_type=relation_type,
                )
            )
        return kg

    def summary(self) -> dict[str, Any]:
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "node_types": list({attrs.get("entity_type") for _, attrs in self.graph.nodes(data=True)}),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_data().model_dump(), ensure_ascii=False)
