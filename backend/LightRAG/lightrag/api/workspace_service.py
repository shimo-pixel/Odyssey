"""
Per-workspace LightRAG instance management for multi-task API support.

Each workspace maps to an isolated knowledge base (KV, vector, graph, doc_status).
Clients select a workspace via the ``LIGHTRAG-WORKSPACE`` HTTP header.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Request

from lightrag.utils import logger, validate_workspace

if TYPE_CHECKING:
    from lightrag import LightRAG
    from lightrag.api.routers.document_routes import DocumentManager


def repair_workspace_encoding(workspace: str) -> str:
    """Repair UTF-8 workspace names mis-decoded as Latin-1 in HTTP headers."""
    if not workspace:
        return workspace
    try:
        repaired = workspace.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return workspace
    return repaired if repaired != workspace else workspace


def latin1_mojibake_form(correct_utf8: str) -> str | None:
    """Return the Latin-1 mojibake alias for a correct UTF-8 workspace name."""
    try:
        return correct_utf8.encode("utf-8").decode("latin-1")
    except UnicodeDecodeError:
        return None


def sanitize_workspace_header(workspace: str) -> str:
    """Normalize workspace header value without stripping non-ASCII task names."""
    ws = repair_workspace_encoding(workspace.strip())
    if not ws:
        return ws
    validate_workspace(ws)
    return ws


def decode_workspace_b64(value: str) -> str:
    """Decode a UTF-8 workspace name from ``LIGHTRAG-WORKSPACE-B64``."""
    padding = "=" * (-len(value) % 4)
    return base64.b64decode((value + padding).encode("ascii")).decode("utf-8")


def workspace_from_request(
    request: Request, default_workspace: str = ""
) -> str:
    """Resolve workspace from B64 or plain header (B64 preferred for Unicode names)."""
    b64 = request.headers.get("LIGHTRAG-WORKSPACE-B64", "").strip()
    if b64:
        try:
            return sanitize_workspace_header(decode_workspace_b64(b64))
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            logger.warning("Invalid LIGHTRAG-WORKSPACE-B64 header: %s", exc)

    workspace = request.headers.get("LIGHTRAG-WORKSPACE", "").strip()
    if not workspace:
        return default_workspace
    return sanitize_workspace_header(workspace)


class WorkspaceService:
    """Lazy registry of LightRAG + DocumentManager instances keyed by workspace."""

    def __init__(
        self,
        *,
        default_workspace: str,
        working_dir: str,
        input_dir: str,
        rag_factory: Callable[[str], LightRAG],
    ) -> None:
        self.default_workspace = default_workspace or ""
        self.working_dir = Path(working_dir)
        self.input_dir = input_dir
        self._rag_factory = rag_factory
        self._rags: dict[str, LightRAG] = {}
        self._doc_managers: dict[str, DocumentManager] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_path = self.working_dir / "workspaces_registry.json"
        self._registry = self._load_registry()
        self._ensure_default_registered()

    def _load_registry(self) -> dict[str, Any]:
        if self._registry_path.exists():
            try:
                data = json.loads(self._registry_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("workspaces"), list):
                    return self._repair_registry_encoding(data)
            except Exception:
                logger.warning("Failed to load workspaces registry, starting fresh")
        return {"workspaces": []}

    def _repair_registry_encoding(self, data: dict[str, Any]) -> dict[str, Any]:
        workspaces = data.get("workspaces", [])
        repaired: list[dict[str, Any]] = []
        seen: set[str] = set()
        changed = False

        for entry in workspaces:
            if not isinstance(entry, dict):
                changed = True
                continue
            workspace_id = str(entry.get("id", ""))
            fixed_id = repair_workspace_encoding(workspace_id)
            if fixed_id != workspace_id:
                changed = True
            if fixed_id in seen:
                changed = True
                continue
            seen.add(fixed_id)
            fixed_entry = dict(entry)
            fixed_entry["id"] = fixed_id
            if str(entry.get("name", "")) == workspace_id:
                fixed_entry["name"] = fixed_id
            repaired.append(fixed_entry)

        if changed:
            data = dict(data)
            data["workspaces"] = repaired
            self._registry_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return data

    def _save_registry(self) -> None:
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(self._registry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_default_registered(self) -> None:
        if not self.default_workspace:
            return
        workspaces = self._registry.setdefault("workspaces", [])
        if not any(w.get("id") == self.default_workspace for w in workspaces):
            workspaces.insert(
                0,
                {
                    "id": self.default_workspace,
                    "name": "Default" if not self.default_workspace else self.default_workspace,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            self._save_registry()

    def _tombstones(self) -> list[str]:
        raw = self._registry.get("tombstones", [])
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if str(item)]

    def _is_tombstoned(self, workspace: str) -> bool:
        return workspace in self._tombstones()

    def _add_tombstone(self, workspace: str) -> None:
        tombstones = self._registry.setdefault("tombstones", [])
        if not isinstance(tombstones, list):
            tombstones = []
            self._registry["tombstones"] = tombstones
        if workspace not in tombstones:
            tombstones.append(workspace)
            self._save_registry()

    def _clear_tombstone(self, workspace: str) -> None:
        tombstones = self._registry.get("tombstones", [])
        if not isinstance(tombstones, list) or workspace not in tombstones:
            return
        self._registry["tombstones"] = [t for t in tombstones if t != workspace]
        self._save_registry()

    def effective_workspace(self, workspace: str) -> str:
        """Reactivate tombstoned workspaces on access.

        A deleted workspace has its storage directory removed and is marked
        with a tombstone. Silently remapping it to the server default would
        cause writes (e.g. imports) targeting the deleted name to pollute the
        default workspace. Instead, treat any new access to a tombstoned
        workspace as a re-creation: clear the tombstone so ``get_rag`` builds
        a fresh storage directory for it.
        """
        if self._is_tombstoned(workspace):
            logger.info(
                "Workspace %r was deleted; reactivating on access",
                workspace,
            )
            self._clear_tombstone(workspace)
        return workspace

    def _lock_for(self, workspace: str) -> asyncio.Lock:
        if workspace not in self._locks:
            self._locks[workspace] = asyncio.Lock()
        return self._locks[workspace]

    def resolve_workspace(self, request: Request | None = None) -> str:
        if request is None:
            ws = self.default_workspace
        else:
            ws = workspace_from_request(request, self.default_workspace)
        validate_workspace(ws)
        return ws

    def get_doc_manager(self, workspace: str) -> DocumentManager:
        from lightrag.api.routers.document_routes import DocumentManager

        validate_workspace(workspace)
        if workspace not in self._doc_managers:
            self._doc_managers[workspace] = DocumentManager(
                self.input_dir, workspace=workspace
            )
        return self._doc_managers[workspace]

    def _migrate_mojibake_workspace_dir(self, workspace: str) -> None:
        ws_dir = self.working_dir / workspace
        if ws_dir.exists():
            return
        alias = latin1_mojibake_form(workspace)
        if not alias:
            return
        alias_dir = self.working_dir / alias
        if alias_dir.is_dir():
            logger.info(
                "Migrating mojibake workspace directory %r -> %r",
                alias,
                workspace,
            )
            alias_dir.rename(ws_dir)
            self._migrate_registry_id(alias, workspace)

    def _migrate_registry_id(self, old_id: str, new_id: str) -> None:
        workspaces = self._registry.setdefault("workspaces", [])
        changed = False
        for entry in workspaces:
            if entry.get("id") == old_id:
                entry["id"] = new_id
                if entry.get("name") == old_id:
                    entry["name"] = new_id
                changed = True
        if changed:
            self._save_registry()

    async def get_rag(self, workspace: str) -> LightRAG:
        validate_workspace(workspace)
        self._migrate_mojibake_workspace_dir(workspace)
        if workspace in self._rags:
            return self._rags[workspace]

        async with self._lock_for(workspace):
            if workspace in self._rags:
                return self._rags[workspace]
            self._migrate_mojibake_workspace_dir(workspace)
            rag = self._rag_factory(workspace)
            await rag.initialize_storages()
            await rag.check_and_migrate_data()
            self._rags[workspace] = rag
            self._register_workspace(workspace)
            return rag

    def _register_workspace(self, workspace: str, name: str | None = None) -> None:
        workspaces = self._registry.setdefault("workspaces", [])
        if any(w.get("id") == workspace for w in workspaces):
            return
        workspaces.append(
            {
                "id": workspace,
                "name": name or (workspace if workspace else "Default"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save_registry()

    def list_workspaces(self) -> list[dict[str, Any]]:
        return list(self._registry.get("workspaces", []))

    async def create_workspace(self, workspace_id: str, name: str | None = None) -> dict:
        validate_workspace(workspace_id)
        display_name = (name or workspace_id).strip() or workspace_id
        self._register_workspace(workspace_id, display_name)
        await self.get_rag(workspace_id)
        self.get_doc_manager(workspace_id)
        return {
            "id": workspace_id,
            "name": display_name,
            "created_at": next(
                (
                    w.get("created_at")
                    for w in self._registry.get("workspaces", [])
                    if w.get("id") == workspace_id
                ),
                None,
            ),
        }

    async def copy_workspace(
        self, source: str, target: str, name: str | None = None
    ) -> dict:
        """Clone a workspace by copying its storage directory on disk.

        Copying files is orders of magnitude cheaper than re-ingesting the
        source documents, which is what makes per-branch knowledge bases
        practical. The target instance is deliberately NOT pre-warmed: the
        first ``get_rag(target)`` must load the freshly copied files instead
        of initializing empty storages that would later overwrite them.
        """
        validate_workspace(source)
        validate_workspace(target)
        if source == target:
            raise ValueError("Source and target workspace must differ")
        if any(w.get("id") == target for w in self._registry.get("workspaces", [])):
            raise FileExistsError(f"Workspace {target!r} already exists")
        if target in self._rags:
            raise FileExistsError(f"Workspace {target!r} is already loaded")

        src_dir = self.working_dir / source
        dst_dir = self.working_dir / target
        if dst_dir.exists():
            raise FileExistsError(f"Storage directory for {target!r} already exists")

        # Flush in-memory state of the source so the copy is not stale.
        src_rag = self._rags.get(source)
        if src_rag is not None:
            for attr in (
                "full_docs",
                "text_chunks",
                "doc_status",
                "chunk_entity_relation_graph",
                "entities_vdb",
                "relationships_vdb",
                "chunks_vdb",
            ):
                storage = getattr(src_rag, attr, None)
                callback = getattr(storage, "index_done_callback", None)
                if callback is None:
                    continue
                try:
                    await callback()
                except Exception as exc:  # best effort flush
                    logger.warning(
                        "Failed to flush %s of workspace %r before copy: %s",
                        attr,
                        source,
                        exc,
                    )

        if src_dir.is_dir():
            shutil.copytree(src_dir, dst_dir)
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)

        src_input = Path(self.input_dir) / source
        if src_input.is_dir():
            shutil.copytree(src_input, Path(self.input_dir) / target)

        self._clear_tombstone(target)
        self._register_workspace(target, name or target)
        return {
            "id": target,
            "name": name or target,
            "source": source,
            "created_at": next(
                (
                    w.get("created_at")
                    for w in self._registry.get("workspaces", [])
                    if w.get("id") == target
                ),
                None,
            ),
        }

    def _remove_workspace_dirs(self, workspace: str) -> None:
        ws_dir = self.working_dir / workspace
        if ws_dir.is_dir():
            shutil.rmtree(ws_dir, ignore_errors=True)
        input_ws = Path(self.input_dir) / workspace
        if input_ws.is_dir():
            shutil.rmtree(input_ws, ignore_errors=True)

    async def delete_workspace(self, workspace: str) -> None:
        if workspace == self.default_workspace:
            raise ValueError("Cannot delete the server default workspace")
        rag = self._rags.pop(workspace, None)
        if rag is not None:
            await rag.finalize_storages()
        self._doc_managers.pop(workspace, None)
        self._registry["workspaces"] = [
            w
            for w in self._registry.get("workspaces", [])
            if w.get("id") != workspace
        ]
        self._add_tombstone(workspace)
        self._save_registry()
        self._remove_workspace_dirs(workspace)

    async def get_rag_for_request(self, request: Request) -> LightRAG:
        return await self.get_rag(self.resolve_workspace(request))

    def get_doc_manager_for_request(self, request: Request) -> DocumentManager:
        return self.get_doc_manager(self.resolve_workspace(request))

    async def resolve_context(
        self, request: Request
    ) -> tuple[LightRAG, DocumentManager]:
        workspace = self.resolve_workspace(request)
        rag = await self.get_rag(workspace)
        return rag, self.get_doc_manager(workspace)

    def make_rag_dependency(self):
        async def get_rag(request: Request) -> LightRAG:
            return await self.get_rag_for_request(request)

        return get_rag

    async def initialize_default(self) -> LightRAG:
        return await self.get_rag(self.default_workspace)

    async def finalize_all(self) -> None:
        for workspace, rag in list(self._rags.items()):
            try:
                await rag.finalize_storages()
            except Exception as exc:
                logger.error("Failed to finalize workspace %s: %s", workspace, exc)
        self._rags.clear()


class StaticWorkspaceService:
    """Single-instance adapter for tests and legacy call sites."""

    def __init__(
        self,
        rag: LightRAG,
        doc_manager: DocumentManager | Any | None = None,
    ) -> None:
        from lightrag.api.routers.document_routes import DocumentManager

        self.default_workspace = getattr(rag, "workspace", "") or ""
        self._rag = rag
        if doc_manager is None or not isinstance(doc_manager, DocumentManager):
            self._doc_manager = DocumentManager("", workspace=self.default_workspace)
        else:
            self._doc_manager = doc_manager

    def resolve_workspace(self, request: Request | None = None) -> str:
        if request is None:
            return self.default_workspace
        return workspace_from_request(request, self.default_workspace)

    async def get_rag(self, workspace: str) -> LightRAG:
        _ = workspace
        return self._rag

    def get_doc_manager(self, workspace: str) -> DocumentManager:
        _ = workspace
        return self._doc_manager

    async def get_rag_for_request(self, request: Request) -> LightRAG:
        return self._rag

    def get_doc_manager_for_request(self, request: Request) -> DocumentManager:
        return self._doc_manager

    async def resolve_context(
        self, request: Request
    ) -> tuple[LightRAG, DocumentManager]:
        return self._rag, self._doc_manager

    def make_rag_dependency(self):
        async def get_rag(request: Request) -> LightRAG:
            return await self.get_rag_for_request(request)

        return get_rag

    async def initialize_default(self) -> LightRAG:
        return self._rag

    async def finalize_all(self) -> None:
        return None
