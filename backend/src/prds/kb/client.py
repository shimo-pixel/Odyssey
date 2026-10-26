"""HTTP client for LightRAG document + workspace APIs."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from typing import Any

import httpx

from prds.config import Settings, get_settings
from prds.simulation.tasks import gather_owned

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

TERMINAL_DOC_STATUSES = {"processed", "failed"}


def normalize_workspace_id(raw: str) -> str:
    """Normalize display name / id into a LightRAG workspace id."""
    text = (raw or "").strip()
    if _SLUG_RE.match(text):
        return text
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
    if not slug:
        slug = f"cat_{uuid.uuid4().hex[:8]}"
    return slug[:64]


def doc_id_for_source(file_source: str) -> str:
    """Reproduce LightRAG's document id for a named text source.

    LightRAG derives the id from the canonical file path
    (``compute_mdhash_id(file_path, prefix="doc-")`` in ``lightrag/pipeline.py``),
    so a snapshot inserted under a fixed ``file_source`` can be deleted later
    without listing the whole workspace first.
    """
    digest = hashlib.md5(file_source.strip().encode("utf-8")).hexdigest()
    return f"doc-{digest}"


class LightRAGClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base = self.settings.prds_lightrag_url.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base, timeout=120.0)

    @staticmethod
    def _ws_headers(workspace: str | None) -> dict[str, str]:
        if not workspace:
            return {}
        return {"LIGHTRAG-WORKSPACE": workspace}

    async def health(self) -> dict[str, Any]:
        try:
            async with self._client() as client:
                r = await client.get("/health")
                if r.status_code == 200:
                    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    return {"ok": True, "status_code": r.status_code, "data": data}
                r2 = await client.get("/")
                return {"ok": r2.status_code < 500, "status_code": r2.status_code, "data": {}}
        except httpx.RequestError as exc:
            return {"ok": False, "error": str(exc)}

    async def list_workspaces(self) -> list[dict[str, Any]]:
        async with self._client() as client:
            r = await client.get("/workspaces")
            if r.status_code >= 400:
                r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("workspaces", "items"):
                    if isinstance(data.get(key), list):
                        return data[key]
            raise RuntimeError("Invalid workspace listing response")

    async def create_workspace(self, workspace_id: str, name: str | None = None) -> dict[str, Any]:
        wid = normalize_workspace_id(workspace_id)
        payload = {"id": wid, "name": (name or wid).strip() or wid}
        async with self._client() as client:
            r = await client.post("/workspaces", json=payload)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"create workspace failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else payload

    async def copy_workspace(
        self, source: str, target: str, name: str | None = None
    ) -> dict[str, Any]:
        """Clone a workspace on the LightRAG side (filesystem copy, no re-index)."""
        payload = {"target_id": normalize_workspace_id(target), "name": name or target}
        async with self._client() as client:
            r = await client.post(f"/workspaces/{source}/copy", json=payload)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"copy workspace failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else payload

    async def delete_workspace(self, workspace_id: str) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.delete(f"/workspaces/{workspace_id}")
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"delete workspace failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            result = r.json() if r.content else {"status": "ok"}
            if result.get("status") not in ("ok", "success", "deleted"):
                raise RuntimeError("Workspace deletion was not completed")
            return result

    async def clear_documents(self, *, workspace: str | None = None) -> dict[str, Any]:
        """Remove all documents and graph data from a workspace."""
        async with self._client() as client:
            r = await client.delete("/documents", headers=self._ws_headers(workspace))
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"LightRAG clear documents failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else {"status": "ok"}

    async def upload(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        *,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        files = {
            "file": (filename, content, content_type or "application/octet-stream"),
        }
        async with self._client() as client:
            r = await client.post(
                "/documents/upload",
                files=files,
                headers=self._ws_headers(workspace),
            )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"LightRAG upload failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json()

    async def list_documents(self, *, workspace: str | None = None) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/documents", headers=self._ws_headers(workspace))
            if r.status_code >= 400:
                r.raise_for_status()
            return r.json()

    async def delete_document(self, doc_id: str, *, workspace: str | None = None) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.request(
                "DELETE",
                "/documents/delete_document",
                json={"doc_ids": [doc_id]},
                headers=self._ws_headers(workspace),
            )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"LightRAG delete failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else {"status": "ok"}

    async def insert_text(
        self,
        text: str,
        file_source: str,
        *,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Insert a named text document; returns the LightRAG track_id."""
        async with self._client() as client:
            r = await client.post(
                "/documents/text",
                json={"text": text, "file_source": file_source},
                headers=self._ws_headers(workspace),
            )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"LightRAG insert text failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else {}

    async def track_status(
        self, track_id: str, *, workspace: str | None = None
    ) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get(
                f"/documents/track_status/{track_id}",
                headers=self._ws_headers(workspace),
            )
            r.raise_for_status()
            return r.json() if r.content else {}

    async def wait_indexed(
        self,
        track_id: str,
        *,
        workspace: str | None = None,
        timeout: float | None = 300.0,
        poll_interval: float = 0.6,
    ) -> bool:
        """Poll a track id until every document reaches a terminal status.

        Returns True only when every document was processed successfully.
        A timeout of None or <= 0 disables the overall wait limit.
        """
        deadline = (asyncio.get_running_loop().time() + timeout
                    if timeout is not None and timeout > 0 else None)
        delay = poll_interval
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            remaining = max(0.001, deadline - asyncio.get_running_loop().time()) if deadline is not None else None
            async with asyncio.timeout(remaining):
                data = await self.track_status(track_id, workspace=workspace)
            documents = data.get("documents") if isinstance(data, dict) else None
            if isinstance(documents, list) and documents:
                statuses = {
                    str(doc.get("status", "")).lower()
                    for doc in documents
                    if isinstance(doc, dict)
                }
                if "failed" in statuses:
                    raise RuntimeError("Knowledge-base indexing failed")
                if statuses == {"processed"}:
                    return True
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 3.0)
        logger.warning(
            "LightRAG indexing wait timed out (track=%s workspace=%s)",
            track_id,
            workspace,
        )
        return False

    async def replace_document(
        self,
        text: str,
        file_source: str,
        *,
        workspace: str,
        wait: bool = True,
        timeout: float | None = 300.0,
    ) -> bool:
        """Delete the previous revision of ``file_source`` then insert a new one.

        Deleting by doc id also removes the entities and relations that only
        that document contributed, which is how a branch's stale state is
        pruned from the graph while the original uploads stay untouched.
        """
        # Disable both the replacement deadline and its nested indexing deadline.
        timeout = timeout if timeout is not None and timeout > 0 else None
        async with asyncio.timeout(timeout):
            doc_id = doc_id_for_source(file_source)
            for attempt in range(3):
                try:
                    deletion = await self.delete_document(doc_id, workspace=workspace)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                    deletion = {"status": "not_found"}
                if deletion.get("status") == "not_allowed":
                    raise RuntimeError("Snapshot deletion is not allowed")
                if deletion.get("status") in ("busy", "deletion_started"):
                    await self.wait_pipeline_idle(workspace=workspace)
                    if deletion["status"] == "busy":
                        if attempt == 2:
                            raise RuntimeError("Snapshot deletion remained busy")
                        continue
                    documents = await self.list_documents(workspace=workspace)
                    if any(doc.get("id") == doc_id
                           for group in documents.get("statuses", {}).values()
                           for doc in group):
                        raise RuntimeError("Previous snapshot was not deleted")
                break
            response = await self.insert_text(text, file_source, workspace=workspace)
            track_id = str(response.get("track_id") or "")
            if not wait or not track_id:
                return bool(track_id)
            return await self.wait_indexed(track_id, workspace=workspace, timeout=timeout)

    async def wait_pipeline_idle(self, *, workspace: str) -> None:
        while True:
            status = await self.pipeline_status(workspace=workspace)
            if "busy" not in status:
                raise RuntimeError("Invalid knowledge-base pipeline status")
            if not status["busy"]:
                return
            await asyncio.sleep(0.3)

    async def pipeline_status(self, *, workspace: str | None = None) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/documents/pipeline_status", headers=self._ws_headers(workspace))
            r.raise_for_status()
            return r.json()

    async def query_data(
        self,
        query: str,
        *,
        workspace: str | None = None,
        mode: str = "mix",
        top_k: int = 20,
        chunk_top_k: int = 10,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retrieve structured RAG data (no LLM answer generation).

        Passing pre-computed keywords lets LightRAG skip its own per-query
        keyword-extraction LLM call, which matters when the same event is
        retrieved across many branches.
        """
        payload: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
            "chunk_top_k": chunk_top_k,
        }
        if hl_keywords:
            payload["hl_keywords"] = hl_keywords
        if ll_keywords:
            payload["ll_keywords"] = ll_keywords
        async with self._client() as client:
            r = await client.post(
                "/query/data",
                json=payload,
                headers=self._ws_headers(workspace),
            )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"LightRAG query/data failed: {r.status_code} {r.text}",
                    request=r.request,
                    response=r,
                )
            return r.json() if r.content else {}

    @staticmethod
    def format_query_data(result: dict[str, Any], *, workspace: str = "") -> str:
        """Flatten query/data response into a readable context block."""
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            data = result if isinstance(result, dict) else {}
        lines: list[str] = []


        entities = data.get("entities") or []
        if isinstance(entities, list) and entities:
            lines.append("#### Entities")
            for ent in entities[:30]:
                if not isinstance(ent, dict):
                    continue
                name = ent.get("entity_name") or ent.get("name") or ""
                etype = ent.get("entity_type") or ""
                desc = ent.get("description") or ""
                lines.append(f"- {name} ({etype}): {desc}".strip())

        relationships = data.get("relationships") or data.get("relations") or []
        if isinstance(relationships, list) and relationships:
            lines.append("#### Relationships")
            for rel in relationships[:30]:
                if not isinstance(rel, dict):
                    continue
                src = rel.get("src_id") or rel.get("source") or rel.get("source_entity") or ""
                tgt = rel.get("tgt_id") or rel.get("target") or rel.get("target_entity") or ""
                rtype = rel.get("description") or rel.get("keywords") or rel.get("relation_type") or ""
                lines.append(f"- {src} → {tgt}: {rtype}".strip())

        chunks = data.get("chunks") or data.get("text_units") or []
        if isinstance(chunks, list) and chunks:
            lines.append("#### Chunks")
            for chunk in chunks[:12]:
                if isinstance(chunk, dict):
                    text = chunk.get("content") or chunk.get("text") or chunk.get("chunk") or ""
                else:
                    text = str(chunk)
                text = str(text).strip()
                if text:
                    lines.append(f"- {text[:800]}")

        formatted = "\n".join(lines).strip()
        return f"### Workspace: {workspace}\n{formatted}" if workspace and formatted else formatted

    async def retrieve_context(
        self,
        query: str,
        workspaces: list[str],
        *,
        max_chars: int = 10000,
        mode: str = "mix",
        top_k: int = 20,
        chunk_top_k: int = 10,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> str:
        """Query several workspaces concurrently and merge the formatted blocks."""
        ids = [w.strip() for w in workspaces if w and str(w).strip()]
        if not ids or not (query or "").strip():
            return ""

        async def one(wid: str) -> str:
            for attempt in range(3):
                try:
                    result = await self.query_data(
                        query, workspace=wid, mode=mode, top_k=top_k,
                        chunk_top_k=chunk_top_k, hl_keywords=hl_keywords, ll_keywords=ll_keywords,
                    )
                    if result.get("status") in ("failure", "failed", "error"):
                        raise RuntimeError("Knowledge-base query failed")
                    return self.format_query_data(result, workspace=wid)
                except (httpx.RequestError, httpx.HTTPStatusError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
        blocks = await gather_owned(*(one(wid) for wid in ids))
        merged = "\n\n".join(b for b in blocks if b).strip()
        if len(merged) > max_chars:
            return merged[: max_chars - 1] + "…"
        return merged

    async def query_contexts(
        self,
        goal: str,
        category_ids: list[str],
        *,
        max_chars: int = 10000,
    ) -> str:
        """Query multiple workspaces and merge into one truncated context string."""
        if not (goal or "").strip():
            return ""
        query = (
            f"与以下决策目标相关的背景、约束、风险、机会与关键事实：\n{goal.strip()}"
        )
        return await self.retrieve_context(query, category_ids, max_chars=max_chars)
