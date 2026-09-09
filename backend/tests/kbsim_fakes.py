"""In-memory stand-ins for LightRAG used by the kbsim tests."""

from __future__ import annotations

from typing import Any

import httpx


class FakeLightRAG:
    """Records every call the pipeline makes against the knowledge base."""

    def __init__(self, *, context: str = "知识库检索结果：上次测验 62 分。") -> None:
        self.context = context
        self.calls: list[tuple[str, tuple, dict]] = []
        self.workspaces: dict[str, str] = {}
        self.documents: dict[str, dict[str, str]] = {}

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def names(self, *wanted: str) -> list[str]:
        return [c[0] for c in self.calls if not wanted or c[0] in wanted]

    def args_for(self, name: str) -> list[tuple[tuple, dict]]:
        return [(a, k) for n, a, k in self.calls if n == name]

    async def query_contexts(self, goal: str, category_ids: list[str], **kwargs: Any) -> str:
        self._record("query_contexts", goal, category_ids)
        return self.context

    async def retrieve_context(self, query: str, workspaces: list[str], **kwargs: Any) -> str:
        self._record("retrieve_context", query, workspaces, **kwargs)
        return self.context

    async def copy_workspace(
        self, source: str, target: str, name: str | None = None
    ) -> dict[str, Any]:
        self._record("copy_workspace", source, target, name)
        self.workspaces[target] = name or target
        self.documents[target] = dict(self.documents.get(source, {}))
        return {"id": target}

    async def create_workspace(self, workspace_id: str, name: str | None = None) -> dict[str, Any]:
        self._record("create_workspace", workspace_id, name)
        self.workspaces[workspace_id] = name or workspace_id
        self.documents.setdefault(workspace_id, {})
        return {"id": workspace_id}

    async def delete_workspace(self, workspace_id: str) -> dict[str, Any]:
        self._record("delete_workspace", workspace_id)
        self.workspaces.pop(workspace_id, None)
        self.documents.pop(workspace_id, None)
        return {"status": "ok"}

    async def list_workspaces(self) -> list[dict[str, Any]]:
        self._record("list_workspaces")
        return [{"id": wid, "name": name} for wid, name in self.workspaces.items()]

    async def delete_document(self, doc_id: str, *, workspace: str | None = None) -> dict[str, Any]:
        self._record("delete_document", doc_id, workspace=workspace)
        return {"status": "ok"}

    async def insert_text(
        self, text: str, file_source: str, *, workspace: str | None = None
    ) -> dict[str, Any]:
        self._record("insert_text", file_source, workspace=workspace)
        self.documents.setdefault(workspace or "", {})[file_source] = text
        return {"track_id": f"track-{file_source}"}

    async def replace_document(
        self, text: str, file_source: str, *, workspace: str, **kwargs: Any
    ) -> bool:
        self._record("replace_document", file_source, workspace=workspace)
        # Mirror the real client's order so tests can assert on it.
        await self.delete_document(f"doc-{file_source}", workspace=workspace)
        await self.insert_text(text, file_source, workspace=workspace)
        return True


def mock_transport_client(handler) -> httpx.AsyncClient:
    """An httpx client whose requests are answered by ``handler``."""
    return httpx.AsyncClient(
        base_url="http://lightrag.test",
        transport=httpx.MockTransport(handler),
    )
