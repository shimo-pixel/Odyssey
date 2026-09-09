"""Knowledge-base routes: categories (workspaces) + documents via LightRAG."""

from __future__ import annotations

import logging
import mimetypes
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from prds.config import get_settings
from prds.kb.client import LightRAGClient, normalize_workspace_id
from prds.storage.models import KbCategory, KbDocument
from prds.storage.repository import SimulationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kb", tags=["knowledge-base"])

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SAFE_NAME_RE = re.compile(r"[^\w.\-]+", re.UNICODE)
_INLINE_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "application/json",
    "application/pdf",
    "application/xml",
    "text/xml",
}

_repo: SimulationRepository | None = None


def get_repo() -> SimulationRepository:
    global _repo
    if _repo is None:
        _repo = SimulationRepository()
    return _repo


class KbDocumentOut(BaseModel):
    id: str
    category_id: str = ""
    filename: str
    track_id: str | None = None
    doc_id: str | None = None
    status: str = "pending"
    size: int = 0
    error: str | None = None
    has_content: bool = False
    created_at: str | None = None


class KbStatusOut(BaseModel):
    lightrag_ok: bool
    lightrag_url: str
    detail: dict = Field(default_factory=dict)


class CategoryCreate(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class CategoryOut(BaseModel):
    id: str
    name: str
    description: str = ""
    document_count: int = 0
    created_at: str | None = None
    lightrag_ok: bool = False


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _require_category(category: str | None) -> str:
    if not category or not category.strip():
        raise HTTPException(status_code=400, detail="category query parameter is required")
    cid = category.strip()
    if not _SLUG_RE.match(cid):
        raise HTTPException(status_code=400, detail="invalid category id")
    return cid


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "file"
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "file"
    return cleaned[:200]


def _resolve_storage_file(storage_path: str | None) -> Path | None:
    if not storage_path:
        return None
    settings = get_settings()
    root = settings.kb_upload_path.resolve()
    candidate = Path(storage_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved


def _store_upload(category_id: str, local_id: str, filename: str, content: bytes) -> str:
    settings = get_settings()
    safe = _safe_filename(filename)
    rel = Path(category_id) / f"{local_id}_{safe}"
    dest = settings.kb_upload_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(rel).replace("\\", "/")


def _unlink_storage(storage_path: str | None) -> None:
    path = _resolve_storage_file(storage_path)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to remove KB file %s: %s", path, exc)


def _rm_category_dir(category_id: str) -> None:
    settings = get_settings()
    folder = (settings.kb_upload_path / category_id).resolve()
    root = settings.kb_upload_path.resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def _doc_out(row: KbDocument) -> KbDocumentOut:
    return KbDocumentOut(
        id=row.id,
        category_id=row.category_id or "",
        filename=row.filename,
        track_id=row.track_id,
        doc_id=row.doc_id,
        status=row.status,
        size=row.size,
        error=row.error,
        has_content=_resolve_storage_file(row.storage_path) is not None,
        created_at=_dt_iso(row.created_at),
    )


async def _find_document(session, doc_key: str, category_id: str) -> KbDocument | None:
    row = await session.get(KbDocument, doc_key)
    if row is None:
        result = await session.execute(
            select(KbDocument).where(
                KbDocument.doc_id == doc_key,
                KbDocument.category_id == category_id,
            )
        )
        row = result.scalar_one_or_none()
    if row is None or (row.category_id and row.category_id != category_id):
        return None
    return row


async def _refresh_remote_statuses(
    client: LightRAGClient, rows: list[KbDocument], workspace: str
) -> None:
    remote_by_id: dict[str, dict] = {}
    try:
        remote = await client.list_documents(workspace=workspace)
        statuses = remote.get("statuses") or remote.get("documents") or {}
        if isinstance(statuses, dict):
            for status_name, docs in statuses.items():
                if not isinstance(docs, list):
                    continue
                for doc in docs:
                    if not isinstance(doc, dict):
                        continue
                    did = str(doc.get("id") or doc.get("doc_id") or "")
                    if did:
                        remote_by_id[did] = {**doc, "status": doc.get("status") or status_name}
        elif isinstance(statuses, list):
            for doc in statuses:
                if isinstance(doc, dict):
                    did = str(doc.get("id") or doc.get("doc_id") or "")
                    if did:
                        remote_by_id[did] = doc
    except Exception as exc:
        logger.warning("Could not refresh LightRAG document list: %s", exc)
        return

    now = datetime.now(timezone.utc)
    for row in rows:
        if row.doc_id and row.doc_id in remote_by_id:
            remote = remote_by_id[row.doc_id]
            new_status = str(remote.get("status") or row.status)
            if new_status != row.status:
                row.status = new_status
                row.updated_at = now


@router.get("/status", response_model=KbStatusOut)
async def kb_status() -> KbStatusOut:
    settings = get_settings()
    client = LightRAGClient(settings)
    health = await client.health()
    return KbStatusOut(
        lightrag_ok=bool(health.get("ok")),
        lightrag_url=settings.prds_lightrag_url,
        detail=health,
    )


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories() -> list[CategoryOut]:
    repo = get_repo()
    client = LightRAGClient()
    health = await client.health()
    lightrag_ok = bool(health.get("ok"))

    remote_map: dict[str, dict] = {}
    if lightrag_ok:
        try:
            for w in await client.list_workspaces():
                wid = str(w.get("id") or "")
                if wid:
                    remote_map[wid] = w
        except Exception as exc:
            logger.warning("list workspaces failed: %s", exc)
            lightrag_ok = False

    async with repo.session_factory() as session:
        local_rows = (
            await session.execute(select(KbCategory).order_by(KbCategory.created_at.desc()))
        ).scalars().all()
        local_by_id = {r.id: r for r in local_rows}

        # Sync display names from LightRAG for categories we already manage locally.
        # Do not auto-import remote workspaces — only user-created categories appear in KB.
        for wid, w in remote_map.items():
            if wid not in local_by_id:
                continue
            name = str(w.get("name") or "").strip()
            if name and local_by_id[wid].name != name:
                local_by_id[wid].name = name

        counts = dict(
            (
                await session.execute(
                    select(KbDocument.category_id, func.count())
                    .group_by(KbDocument.category_id)
                )
            ).all()
        )
        await session.commit()

        out: list[CategoryOut] = []
        for cid, local in local_by_id.items():
            remote = remote_map.get(cid) or {}
            name = local.name or remote.get("name") or cid
            created = _dt_iso(local.created_at)
            out.append(
                CategoryOut(
                    id=cid,
                    name=name,
                    description=local.description or "",
                    document_count=int(counts.get(cid) or 0),
                    created_at=created,
                    lightrag_ok=lightrag_ok and cid in remote_map if remote_map else lightrag_ok,
                )
            )
        out.sort(key=lambda c: c.created_at or "", reverse=True)
        return out


@router.post("/categories", response_model=CategoryOut)
async def create_category(body: CategoryCreate) -> CategoryOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    description = (body.description or "").strip()
    raw_id = (body.id or name).strip()
    cid = normalize_workspace_id(raw_id)
    if not _SLUG_RE.match(cid):
        raise HTTPException(status_code=400, detail="invalid category id")

    repo = get_repo()
    client = LightRAGClient()

    async with repo.session_factory() as session:
        existing = await session.get(KbCategory, cid)
        if existing is not None:
            raise HTTPException(status_code=409, detail="category already exists")

    try:
        await client.create_workspace(cid, name)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"LightRAG unreachable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        # 400 may mean already exists remotely — still create local
        if exc.response is not None and exc.response.status_code not in (400, 409):
            raise HTTPException(
                status_code=502, detail=f"create workspace failed: {exc.response.text}"
            ) from exc

    async with repo.session_factory() as session:
        row = KbCategory(id=cid, name=name, description=description)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return CategoryOut(
            id=row.id,
            name=row.name,
            description=row.description or "",
            document_count=0,
            created_at=_dt_iso(row.created_at),
            lightrag_ok=True,
        )


async def _purge_lightrag_workspace(client: LightRAGClient, workspace_id: str) -> None:
    """Clear remote documents then delete the LightRAG workspace."""
    try:
        await client.clear_documents(workspace=workspace_id)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"LightRAG unreachable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status not in (404, 409):
            logger.warning("LightRAG clear documents warning for %s: %s", workspace_id, exc)

    try:
        await client.delete_workspace(workspace_id)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"LightRAG unreachable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 404:
            logger.info("LightRAG workspace %s already absent", workspace_id)
            return
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to delete LightRAG workspace: "
                f"{exc.response.text if exc.response is not None else exc}"
            ),
        ) from exc


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str) -> dict:
    cid = _require_category(category_id)
    repo = get_repo()
    client = LightRAGClient()

    await _purge_lightrag_workspace(client, cid)

    async with repo.session_factory() as session:
        docs = (
            await session.execute(select(KbDocument).where(KbDocument.category_id == cid))
        ).scalars().all()
        for doc in docs:
            _unlink_storage(doc.storage_path)
        await session.execute(delete(KbDocument).where(KbDocument.category_id == cid))
        row = await session.get(KbCategory, cid)
        if row is not None:
            await session.delete(row)
        await session.commit()
    _rm_category_dir(cid)
    return {"status": "deleted", "id": cid}


@router.get("/documents", response_model=list[KbDocumentOut])
async def list_documents(category: str = Query(...)) -> list[KbDocumentOut]:
    cid = _require_category(category)
    repo = get_repo()
    client = LightRAGClient()

    async with repo.session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(KbDocument)
                    .where(KbDocument.category_id == cid)
                    .order_by(KbDocument.created_at.desc())
                )
            ).scalars().all()
        )
        await _refresh_remote_statuses(client, rows, cid)
        await session.commit()
        return [_doc_out(row) for row in rows]


@router.post("/documents", response_model=KbDocumentOut)
async def upload_document(
    category: str = Query(...),
    file: UploadFile = File(...),
) -> KbDocumentOut:
    cid = _require_category(category)
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    repo = get_repo()
    client = LightRAGClient()
    local_id = str(uuid.uuid4())
    track_id = None
    doc_id = None
    status = "uploaded"
    error = None
    storage_path = _store_upload(cid, local_id, file.filename, content)

    try:
        result = await client.upload(file.filename, content, file.content_type, workspace=cid)
        track_id = result.get("track_id") or result.get("tracking_id")
        doc_id = result.get("doc_id") or result.get("id")
        status = result.get("status") or "processing"
        if not doc_id and isinstance(result.get("data"), dict):
            doc_id = result["data"].get("doc_id") or result["data"].get("id")
    except httpx.HTTPStatusError as exc:
        status = "error"
        error = str(exc)[:1000]
        logger.exception("LightRAG upload failed")
    except httpx.RequestError as exc:
        _unlink_storage(storage_path)
        raise HTTPException(status_code=503, detail=f"LightRAG unreachable: {exc}") from exc

    async with repo.session_factory() as session:
        # Ensure category exists locally
        cat = await session.get(KbCategory, cid)
        if cat is None:
            session.add(KbCategory(id=cid, name=cid))
        row = KbDocument(
            id=local_id,
            category_id=cid,
            filename=file.filename,
            track_id=track_id,
            doc_id=doc_id,
            status=status,
            size=len(content),
            error=error,
            storage_path=storage_path,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        if status == "error":
            raise HTTPException(status_code=502, detail=error or "upload failed")
        return _doc_out(row)


@router.get("/documents/{doc_key}/content")
async def get_document_content(
    doc_key: str,
    category: str = Query(...),
) -> FileResponse:
    """Stream the stored original file for preview / download."""
    cid = _require_category(category)
    repo = get_repo()

    async with repo.session_factory() as session:
        row = await _find_document(session, doc_key, cid)
        if row is None:
            raise HTTPException(status_code=404, detail="document not found")
        path = _resolve_storage_file(row.storage_path)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail="original file unavailable; re-upload to preview",
            )
        filename = row.filename or path.name
        guessed, _ = mimetypes.guess_type(filename)
        media_type = guessed or "application/octet-stream"
        disposition = "inline" if media_type in _INLINE_TYPES or media_type.startswith("text/") else "attachment"
        return FileResponse(
            path,
            media_type=media_type,
            filename=filename,
            content_disposition_type=disposition,
        )


@router.delete("/documents/{doc_key}")
async def delete_document(
    doc_key: str,
    category: str = Query(...),
) -> dict:
    """Delete by local id or LightRAG doc_id within a category."""
    cid = _require_category(category)
    repo = get_repo()
    client = LightRAGClient()

    async with repo.session_factory() as session:
        row = await _find_document(session, doc_key, cid)
        if row is None:
            raise HTTPException(status_code=404, detail="document not found")

        try:
            if row.doc_id:
                await client.delete_document(row.doc_id, workspace=cid)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"LightRAG unreachable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("LightRAG delete warning: %s", exc)

        _unlink_storage(row.storage_path)
        await session.delete(row)
        await session.commit()
        return {"status": "deleted", "id": doc_key}
