"""Episode-driven GraphRAG backend on Graphiti + Neo4j.

This is the "底层" the product spec asks for: text (the seed document and, during
the simulation, agent-behaviour narratives) is streamed into Graphiti as
*episodes*; Graphiti uses an LLM to auto-extract entities and relationships and
persists them in Neo4j as a temporal knowledge graph that grows with the run.

Everything here is import-guarded and async-native (Odyssey runs on asyncio).
When ``graphiti-core`` isn't installed, Neo4j isn't reachable, or no embedder is
configured, :class:`GraphitiStore` reports ``available == False`` and callers
fall back to the in-house incremental builder.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from prds.config import Settings, get_settings

logger = logging.getLogger(__name__)

try:  # graphiti-core is an optional dependency
    from graphiti_core import Graphiti  # type: ignore
    from graphiti_core.nodes import EpisodeType  # type: ignore

    _GRAPHITI_IMPORTABLE = True
except Exception:  # pragma: no cover - depends on optional install
    Graphiti = None  # type: ignore
    EpisodeType = None  # type: ignore
    _GRAPHITI_IMPORTABLE = False


def graphiti_importable() -> bool:
    return _GRAPHITI_IMPORTABLE


def _needs_ipv4_transport(base_url: str | None) -> bool:
    """DashScope endpoints often fail TLS over IPv6 on some Linux networks."""
    return bool(base_url and "dashscope" in base_url.lower())


def _dashscope_embedder(config: Any, client: Any) -> Any:
    """OpenAIEmbedder with chunked batches for DashScope text-embedding-v4 (max 10)."""
    from graphiti_core.embedder.openai import OpenAIEmbedder

    class DashScopeEmbedder(OpenAIEmbedder):
        MAX_BATCH = 10

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            if len(input_data_list) <= self.MAX_BATCH:
                return await super().create_batch(input_data_list)
            out: list[list[float]] = []
            for i in range(0, len(input_data_list), self.MAX_BATCH):
                chunk = input_data_list[i : i + self.MAX_BATCH]
                out.extend(await super().create_batch(chunk))
            return out

    return DashScopeEmbedder(config=config, client=client)


def _openai_async_client(api_key: str, base_url: str | None, *, timeout: float = 300) -> Any:
    """Build AsyncOpenAI client; force IPv4 for DashScope when needed."""
    from openai import AsyncOpenAI

    if not _needs_ipv4_transport(base_url):
        return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    import httpx

    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    http_client = httpx.AsyncClient(transport=transport, timeout=timeout)
    return AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client)


class GraphitiStore:
    """Thin async wrapper around a Graphiti instance bound to one Neo4j database.

    Each simulation is isolated by ``group_id == simulation_id``.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._graphiti: Any = None
        self._driver: Any = None
        self._initialized = False

    @property
    def available(self) -> bool:
        return (
            _GRAPHITI_IMPORTABLE
            and self.settings.neo4j_enabled
            and self.settings.graphiti_embedding_configured
        )

    # -- lifecycle ---------------------------------------------------------

    async def _ensure_init(self) -> bool:
        if self._initialized:
            return True
        if not self.available:
            return False
        try:
            llm_client = self._build_llm_client()
            embedder = self._build_embedder()
            cross_encoder = self._build_cross_encoder()
            self._graphiti = Graphiti(
                self.settings.neo4j_uri,
                self.settings.neo4j_user,
                self.settings.neo4j_password,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder,
            )
            await self._graphiti.build_indices_and_constraints()
            self._driver = self._graphiti.driver
            self._initialized = True
            logger.info("Graphiti store initialized (Neo4j=%s)", self.settings.neo4j_uri)
            return True
        except Exception as exc:
            logger.warning("Graphiti init failed, falling back to builtin graph: %s", exc)
            self._graphiti = None
            self._initialized = False
            return False

    def _build_llm_client(self) -> Any:
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

        api_key, base_url, model = self._resolve_graphiti_llm()
        config = LLMConfig(api_key=api_key, base_url=base_url, model=model, temperature=0)
        client = _openai_async_client(
            api_key, base_url, timeout=float(self.settings.graphiti_async_timeout_s)
        )
        return OpenAIGenericClient(config=config, client=client)

    def _build_embedder(self) -> Any:
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

        api_key, base_url, model = self._resolve_graphiti_embedding()
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if model:
            kwargs["embedding_model"] = model
        client = _openai_async_client(
            api_key, base_url, timeout=float(self.settings.graphiti_async_timeout_s)
        )
        config = OpenAIEmbedderConfig(**kwargs)
        if _needs_ipv4_transport(base_url):
            return _dashscope_embedder(config, client)
        return OpenAIEmbedder(config=config, client=client)

    def _build_cross_encoder(self) -> Any:
        """Graphiti defaults to OpenAIRerankerClient() which requires OPENAI_API_KEY in env."""
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.llm_client.config import LLMConfig

        api_key, base_url, model = self._resolve_graphiti_llm()
        config = LLMConfig(api_key=api_key, base_url=base_url, model=model, temperature=0)
        client = _openai_async_client(
            api_key, base_url, timeout=float(self.settings.graphiti_async_timeout_s)
        )
        return OpenAIRerankerClient(config=config, client=client)

    def _resolve_graphiti_llm(self) -> tuple[str, str | None, str]:
        """Pick API key, base URL, and model for Graphiti's OpenAI-compatible LLM client."""
        s = self.settings
        if s.graphiti_llm_model:
            api_key = (
                s.graphiti_llm_api_key
                or s.graphiti_embedding_api_key
                or s.openai_api_key
                or s.deepseek_api_key
            )
            base_url = (
                s.graphiti_llm_api_base
                or s.graphiti_embedding_api_base
                or None
            )
            return api_key, base_url, s.graphiti_llm_model

        model = s.prds_llm_model_analysis or s.prds_llm_model
        if self._is_deepseek_routing(model):
            api_key = s.deepseek_api_key or s.openai_api_key
            base_url = s.prds_llm_api_base or "https://api.deepseek.com/v1"
            if model.lower().startswith("deepseek"):
                model = "deepseek-chat"
            return api_key, base_url, model
        api_key = s.openai_api_key or s.deepseek_api_key
        base_url = s.prds_llm_api_base or None
        return api_key, base_url, model

    def _resolve_graphiti_embedding(self) -> tuple[str, str | None, str | None]:
        """Embeddings need a real OpenAI-compatible embedder (DeepSeek has no embedding API)."""
        s = self.settings
        api_key = s.graphiti_embedding_api_key or ""
        base_url = s.graphiti_embedding_api_base or None
        model = s.graphiti_embedding_model or None
        if not api_key and not self._is_deepseek_routing():
            api_key = s.openai_api_key
        if not base_url and api_key and not self._is_deepseek_routing():
            base_url = s.prds_llm_api_base or None
        return api_key, base_url, model

    def _is_deepseek_routing(self, model: str | None = None) -> bool:
        s = self.settings
        if s.graphiti_llm_model and not s.graphiti_llm_model.lower().startswith("deepseek"):
            return False
        model = (model or s.graphiti_llm_model or s.prds_llm_model_analysis or s.prds_llm_model).lower()
        if model.startswith("deepseek"):
            return True
        if s.prds_llm_api_base and "deepseek" in s.prds_llm_api_base.lower():
            return True
        # Common misconfig: DeepSeek key copied into OPENAI_API_KEY with no base URL.
        if s.deepseek_api_key and s.openai_api_key == s.deepseek_api_key:
            return True
        return bool(s.deepseek_api_key and not s.openai_api_key)

    async def close(self) -> None:
        if self._graphiti is not None:
            try:
                await self._graphiti.close()
            except Exception:
                pass
        self._graphiti = None
        self._initialized = False

    # -- episode ingestion -------------------------------------------------

    async def add_episode(
        self,
        group_id: str,
        body: str,
        *,
        name: str,
        source_description: str = "odyssey_simulation",
        reference_time: datetime | None = None,
    ) -> bool:
        if not body.strip():
            return False
        if not await self._ensure_init():
            return False
        try:
            await self._graphiti.add_episode(
                name=name,
                episode_body=body,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=reference_time or datetime.now(timezone.utc),
                group_id=group_id,
            )
            return True
        except Exception as exc:
            logger.warning("Graphiti add_episode failed (group=%s): %s", group_id, exc)
            return False

    async def delete_graph(self, group_id: str) -> None:
        if not await self._ensure_init():
            return
        try:
            await self._driver.execute_query(
                "MATCH (n {group_id: $gid}) DETACH DELETE n",
                gid=group_id,
            )
        except Exception as exc:
            logger.warning("Graphiti delete_graph failed (group=%s): %s", group_id, exc)

    # -- read back for visualization --------------------------------------

    async def get_graph_data(self, group_id: str) -> dict[str, Any] | None:
        """Return ``{nodes, edges}`` in Graphiti shape, or None if unavailable."""
        if not await self._ensure_init():
            return None
        try:
            nodes = await self._read_nodes(group_id)
            edges = await self._read_edges(group_id)
            return {
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }
        except Exception as exc:
            logger.warning("Graphiti get_graph_data failed (group=%s): %s", group_id, exc)
            return None

    async def _read_nodes(self, group_id: str) -> list[dict[str, Any]]:
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (n:Entity {group_id: $gid})
            RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                   n.summary AS summary, properties(n) AS props, n.created_at AS created_at
            """,
            gid=group_id,
        )
        out: list[dict[str, Any]] = []
        for r in records:
            props = r.get("props", {}) or {}
            attributes = {
                k: v
                for k, v in props.items()
                if k not in {"uuid", "name", "summary", "created_at", "group_id", "name_embedding"}
            }
            out.append(
                {
                    "uuid": r.get("uuid", ""),
                    "name": r.get("name", ""),
                    "labels": r.get("labels", ["Entity"]),
                    "summary": r.get("summary", "") or "",
                    "attributes": attributes,
                    "created_at": _iso(r.get("created_at")),
                }
            )
        return out

    async def _read_edges(self, group_id: str) -> list[dict[str, Any]]:
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (n:Entity {group_id: $gid})-[r]->(m:Entity {group_id: $gid})
            RETURN DISTINCT r.uuid AS uuid, COALESCE(r.name, type(r)) AS name,
                   r.fact AS fact, startNode(r).uuid AS source, endNode(r).uuid AS target,
                   r.created_at AS created_at
            """,
            gid=group_id,
        )
        out: list[dict[str, Any]] = []
        for r in records:
            out.append(
                {
                    "uuid": r.get("uuid", ""),
                    "name": r.get("name", "RELATED"),
                    "fact": r.get("fact", "") or "",
                    "source_node_uuid": r.get("source", ""),
                    "target_node_uuid": r.get("target", ""),
                    "created_at": _iso(r.get("created_at")),
                }
            )
        return out


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "to_native"):
        try:
            return value.to_native().isoformat()
        except Exception:
            return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


_store: GraphitiStore | None = None


def get_graphiti_store() -> GraphitiStore:
    global _store
    if _store is None:
        _store = GraphitiStore()
    return _store
