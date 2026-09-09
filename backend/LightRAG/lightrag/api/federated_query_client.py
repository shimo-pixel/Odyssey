"""
Python client for federated LightRAG query API.

Use from task-space services to query multiple domain LightRAG deployments
without importing domain data locally.
"""

from __future__ import annotations

from typing import Any

import httpx


class FederatedLightRagClient:
    def __init__(
        self,
        orchestrator_base_url: str,
        *,
        api_key: str | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self.base_url = orchestrator_base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_sec = timeout_sec

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        return headers

    async def query(
        self,
        query: str,
        *,
        task_space_id: str | None = None,
        domains: list[dict[str, Any]] | None = None,
        mode: str = "mix",
        top_k: int | None = None,
        chunk_top_k: int | None = None,
        include_references: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "include_references": include_references,
        }
        if task_space_id:
            body["task_space_id"] = task_space_id
        if domains:
            body["domains"] = domains
        if top_k is not None:
            body["top_k"] = top_k
        if chunk_top_k is not None:
            body["chunk_top_k"] = chunk_top_k

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(
                f"{self.base_url}/federated/query",
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def query_data(
        self,
        query: str,
        *,
        task_space_id: str | None = None,
        domains: list[dict[str, Any]] | None = None,
        mode: str = "mix",
        top_k: int | None = None,
        chunk_top_k: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "mode": mode}
        if task_space_id:
            body["task_space_id"] = task_space_id
        if domains:
            body["domains"] = domains
        if top_k is not None:
            body["top_k"] = top_k
        if chunk_top_k is not None:
            body["chunk_top_k"] = chunk_top_k

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(
                f"{self.base_url}/federated/query/data",
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
            return response.json()
