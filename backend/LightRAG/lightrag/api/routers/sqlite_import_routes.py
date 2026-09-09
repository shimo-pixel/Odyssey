"""
SQLite → natural language → knowledge graph import routes.
"""

from __future__ import annotations

import traceback
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from lightrag import LightRAG
from lightrag.api.sqlite_import_service import (
    SqliteTableConversionResult,
    delete_sqlite_table_document,
    detect_import_source_type,
    import_csv_file,
    import_csv_file_as_json,
    import_sqlite_tables_as_json,
    list_sqlite_tables,
    parse_sqlite_import_bool_form,
    parse_sqlite_import_tables_form,
    probe_import_models,
    resolve_import_source_path,
    resolve_sqlite_database_path,
    resolve_sqlite_table_reference,
    save_uploaded_csv_file,
    save_uploaded_sqlite_database,
)
from lightrag.api.workspace_service import WorkspaceService, sanitize_workspace_header, workspace_from_request
from lightrag.utils import generate_track_id, logger

from ..utils_api import get_combined_auth_dependency
from .document_routes import (
    TextChunkingConfig,
    _acquire_destructive_busy,
    _release_destructive_busy,
    _release_enqueue_slot,
    _reserve_enqueue_slot,
    _resolve_text_chunking,
    get_doc_status_value,
    get_existing_doc_by_file_path_candidates,
    normalize_file_path,
    pipeline_index_texts,
)


class SqliteTablesResponse(BaseModel):
    database_path: str
    tables: list[str]


class SqliteImportRequest(BaseModel):
    database_path: str = Field(
        ...,
        description=(
            "Path to a SQLite database (.db/.sqlite/.sqlite3) or CSV file "
            "(.csv/.tsv) on the server"
        ),
        examples=["./data/knowledge.db"],
    )
    source_type: Literal["sqlite", "csv", "auto"] = Field(
        default="auto",
        description="Import format; auto-detect from file extension when omitted",
    )
    csv_delimiter: Optional[str] = Field(
        default=None,
        description="CSV column delimiter (auto-detect when omitted)",
        examples=[",", ";", "tab"],
    )
    dataset_name: Optional[str] = Field(
        default=None,
        description="Display name for CSV dataset in LLM natural-language output",
    )
    tables: Optional[list[str]] = Field(
        default=None,
        description="Tables to import; omit to import all user tables",
        examples=[["players", "teams"]],
    )
    max_rows_per_table: int = Field(
        default=200,
        ge=1,
        le=5000,
        description="Maximum rows read per table before LLM conversion",
    )
    language: str = Field(
        default="Chinese",
        description="Output language for the natural-language conversion step",
    )
    file_source_prefix: Optional[str] = Field(
        default="sqlite_import",
        description="Prefix for generated file_source values passed to /documents/text",
    )
    chunking: Optional[TextChunkingConfig] = Field(
        default=None,
        description="Optional chunking config (same as /documents/text)",
    )
    resolve_cross_table_links: bool = Field(
        default=True,
        description=(
            "When true, resolve *_id foreign keys to canonical entity names across "
            "tables and pass a cross-table entity registry as LLM guidance (not "
            "imported as a separate document)."
        ),
    )

    @field_validator("tables", mode="before")
    @classmethod
    def normalize_tables(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            return [value]
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "database_path": "./data/knowledge.db",
                "tables": ["players", "teams"],
                "max_rows_per_table": 200,
                "language": "Chinese",
                "file_source_prefix": "sqlite_import",
            }
        }
    )


class SqliteTableImportResultResponse(BaseModel):
    table: str
    file_source: str
    track_id: str
    row_count: int
    text_chars: int
    status: Literal["queued", "skipped", "failed", "json_queued"]
    error: Optional[str] = None


class SqliteImportJobResponse(BaseModel):
    status: Literal["started"]
    message: str
    job_id: str
    database_path: str
    tables: list[str]


class SqliteImportResponse(BaseModel):
    status: Literal["success", "partial_success", "failure", "json_deferred"]
    message: str
    source_type: Literal["sqlite", "csv"]
    database_path: str
    results: list[SqliteTableImportResultResponse]


class SqliteTableTargetRequest(BaseModel):
    """Upload or delete one SQLite table in a task workspace."""

    task_space_id: str = Field(
        ...,
        description="任务空间 ID，须与请求头 LIGHTRAG-WORKSPACE 一致",
        examples=["task_id_2"],
    )
    database_path: str = Field(
        ...,
        description="SQLite 数据库文件路径",
        examples=["/home/shimo/dts-server/.dts/military-task.db"],
    )
    table_name: Optional[str] = Field(
        default=None,
        description="SQLite 物理表名（与 table_id 二选一）",
        examples=["pilot"],
    )
    table_id: Optional[str] = Field(
        default=None,
        description="资源/元数据表 ID（与 table_name 二选一），可在库内 dts_meta_object 等目录表解析",
        examples=["meta-mil-001", "pilot"],
    )
    file_source_prefix: Optional[str] = Field(
        default=None,
        description="导入文档 file_source 前缀；省略时与历史 sqlite 导入保持一致",
    )

    @field_validator("table_name", "table_id", mode="before")
    @classmethod
    def strip_optional(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_space_id": "task_id_2",
                "database_path": "/data/military-task.db",
                "table_name": "pilot",
            }
        }
    )


class SqliteTableUploadRequest(SqliteTableTargetRequest):
    max_rows_per_table: int = Field(
        default=200,
        ge=1,
        le=5000,
        description="单表最大读取行数",
    )
    language: str = Field(default="Chinese", description="自然语言转换输出语言")
    chunking: Optional[TextChunkingConfig] = Field(
        default=None,
        description="可选分块配置（同 /documents/text）",
    )
    resolve_cross_table_links: bool = Field(
        default=True,
        description="是否解析跨表外键并注入实体索引上下文",
    )
    replace_if_exists: bool = Field(
        default=False,
        description="若该表文档已存在，先删除再重新上传",
    )


class SqliteTableDeleteRequest(SqliteTableTargetRequest):
    delete_llm_cache: bool = Field(
        default=False,
        description="删除文档时是否同时清理 LLM 抽取缓存",
    )


class SqliteTableUploadResponse(BaseModel):
    status: Literal["success", "skipped", "failure"]
    message: str
    task_space_id: str
    database_path: str
    table: str
    file_source: str
    track_id: Optional[str] = None
    row_count: int = 0
    text_chars: int = 0
    error: Optional[str] = None


class SqliteTableDeleteResponse(BaseModel):
    status: Literal["success", "not_found", "busy", "failure"]
    message: str
    task_space_id: str
    database_path: str
    table: str
    file_source: str
    doc_id: Optional[str] = None
    error: Optional[str] = None


def _validate_task_space_id(request: Request, task_space_id: str) -> str:
    expected = sanitize_workspace_header(task_space_id.strip())
    if not expected:
        raise HTTPException(status_code=422, detail="task_space_id is required")
    header_ws = workspace_from_request(request, default_workspace="")
    if header_ws and header_ws != expected:
        raise HTTPException(
            status_code=400,
            detail=(
                f"task_space_id '{expected}' does not match "
                f"LIGHTRAG-WORKSPACE header '{header_ws}'"
            ),
        )
    if not header_ws:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing LIGHTRAG-WORKSPACE header; set it to '{expected}' "
                "to select the task workspace"
            ),
        )
    return expected


def _validate_table_target(body: SqliteTableTargetRequest) -> None:
    if not body.table_name and not body.table_id:
        raise HTTPException(
            status_code=422,
            detail="Either table_name or table_id is required",
        )
    if body.table_name and body.table_id:
        raise HTTPException(
            status_code=422,
            detail="Provide either table_name or table_id, not both",
        )


def _to_response_result(item: SqliteTableConversionResult) -> SqliteTableImportResultResponse:
    return SqliteTableImportResultResponse(
        table=item.table,
        file_source=item.file_source,
        track_id=item.track_id,
        row_count=item.row_count,
        text_chars=item.text_chars,
        status=item.status,  # type: ignore[arg-type]
        error=item.error,
    )


def _summarize_status(
    results: list[SqliteTableConversionResult],
    *,
    source_type: Literal["sqlite", "csv"],
) -> str:
    queued = sum(1 for r in results if r.status == "queued")
    json_queued = sum(1 for r in results if r.status == "json_queued")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    label = "CSV" if source_type == "csv" else "SQLite"
    return (
        f"{label} import finished: {queued} queued, {json_queued} json-deferred, "
        f"{skipped} skipped, {failed} failed."
    )


def _resolve_request_source_type(body: SqliteImportRequest) -> Literal["sqlite", "csv"]:
    if body.source_type in {"sqlite", "csv"}:
        return body.source_type
    return detect_import_source_type(body.database_path)


async def _parse_import_sync_request(http_request: Request, rag: LightRAG) -> SqliteImportRequest:
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(
                status_code=400,
                detail="multipart/form-data request requires a 'file' field",
            )

        original_filename = getattr(upload, "filename", None) or ""
        source_type_raw = form.get("source_type")
        source_type = (
            str(source_type_raw).strip().lower()
            if source_type_raw not in (None, "")
            else "auto"
        )
        if source_type not in {"sqlite", "csv", "auto"}:
            raise HTTPException(
                status_code=422,
                detail="source_type must be sqlite, csv, or auto",
            )

        if source_type == "auto":
            try:
                source_type = detect_import_source_type(original_filename or "upload.db")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Unable to detect import type from filename; use .db/.sqlite "
                        "or .csv/.tsv, or set source_type explicitly"
                    ),
                ) from None

        if source_type == "csv":
            saved = await save_uploaded_csv_file(
                upload,
                working_dir=rag.working_dir,
                original_filename=original_filename,
            )
        else:
            saved = await save_uploaded_sqlite_database(
                upload,
                working_dir=rag.working_dir,
                original_filename=original_filename,
            )

        tables_raw = form.get("tables")
        max_rows_raw = form.get("max_rows_per_table")
        language_raw = form.get("language")
        prefix_raw = form.get("file_source_prefix")
        resolve_links_raw = form.get("resolve_cross_table_links")
        csv_delimiter_raw = form.get("csv_delimiter")
        dataset_name_raw = form.get("dataset_name")

        default_prefix = "csv_import" if source_type == "csv" else "sqlite_import"

        try:
            max_rows = int(max_rows_raw) if max_rows_raw not in (None, "") else 200
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="max_rows_per_table must be an integer",
            ) from exc

        try:
            return SqliteImportRequest(
                database_path=str(saved),
                source_type=source_type,
                tables=parse_sqlite_import_tables_form(
                    str(tables_raw) if tables_raw is not None else None
                ),
                max_rows_per_table=max_rows,
                language=str(language_raw).strip() if language_raw else "Chinese",
                file_source_prefix=(
                    str(prefix_raw).strip() if prefix_raw else default_prefix
                ),
                resolve_cross_table_links=parse_sqlite_import_bool_form(
                    str(resolve_links_raw) if resolve_links_raw is not None else None
                ),
                csv_delimiter=(
                    str(csv_delimiter_raw).strip()
                    if csv_delimiter_raw not in (None, "")
                    else None
                ),
                dataset_name=(
                    str(dataset_name_raw).strip()
                    if dataset_name_raw not in (None, "")
                    else None
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        payload = await http_request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Request body must be JSON or multipart/form-data with a file upload",
        ) from exc
    return SqliteImportRequest(**payload)


def _build_upload_only_response(
    body: SqliteImportRequest,
    *,
    working_dir: str,
    source_type: Literal["sqlite", "csv"],
    reason: str,
) -> SqliteImportResponse:
    """Legacy fallback when JSON staging also fails."""
    source_path, _ = resolve_import_source_path(
        body.database_path, working_dir=working_dir
    )
    if source_type == "csv":
        stored_label = "raw CSV file"
    else:
        stored_label = "raw SQLite database"
    return SqliteImportResponse(
        status="json_deferred",
        message=(
            f"Could not stage JSON documents; stored the {stored_label} only "
            f"({reason})."
        ),
        source_type=source_type,
        database_path=str(source_path),
        results=[],
    )


def _build_import_sync_response(
    body: SqliteImportRequest,
    results: list[SqliteTableConversionResult],
    *,
    working_dir: str,
    source_type: Literal["sqlite", "csv"],
    models_unavailable_reason: str | None = None,
) -> SqliteImportResponse:
    queued = sum(1 for r in results if r.status == "queued")
    json_queued = sum(1 for r in results if r.status == "json_queued")
    failed = sum(1 for r in results if r.status == "failed")
    if (queued or json_queued) and failed:
        status: Literal["success", "partial_success", "failure", "json_deferred"] = (
            "partial_success"
        )
    elif queued:
        status = "success"
    elif json_queued:
        status = "json_deferred"
    else:
        status = "failure"

    source_path, _ = resolve_import_source_path(
        body.database_path, working_dir=working_dir
    )
    message = _summarize_status(results, source_type=source_type)
    if json_queued and models_unavailable_reason:
        message = (
            f"{message} Models unavailable ({models_unavailable_reason}); "
            "JSON documents are visible in the document list as incomplete."
        )
    return SqliteImportResponse(
        status=status,
        message=message,
        source_type=source_type,
        database_path=str(source_path),
        results=[_to_response_result(r) for r in results],
    )


def create_sqlite_import_routes(
    workspace_service: WorkspaceService | LightRAG,
    api_key: Optional[str] = None,
):
    if not isinstance(workspace_service, WorkspaceService):
        from lightrag.api.workspace_service import StaticWorkspaceService

        workspace_service = StaticWorkspaceService(workspace_service)

    router = APIRouter(prefix="/sqlite", tags=["sqlite"])
    combined_auth = get_combined_auth_dependency(api_key)

    async def _resolve(request: Request) -> LightRAG:
        rag, _doc_manager = await workspace_service.resolve_context(request)
        return rag

    @router.get(
        "/tables",
        response_model=SqliteTablesResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def get_sqlite_tables(
        request: Request,
        database_path: str = Query(..., description="Path to SQLite database file"),
    ):
        """List importable tables in a SQLite database."""
        rag = await _resolve(request)
        try:
            db_path = resolve_sqlite_database_path(
                database_path, working_dir=rag.working_dir
            )
            tables = list_sqlite_tables(db_path)
            return SqliteTablesResponse(
                database_path=str(db_path),
                tables=tables,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to list SQLite tables: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def _run_import_sync(
        rag: LightRAG,
        body: SqliteImportRequest,
    ) -> tuple[list[SqliteTableConversionResult], Literal["sqlite", "csv"]]:
        source_type = _resolve_request_source_type(body)

        if body.chunking is not None:
            _resolve_text_chunking(body.chunking, rag)

        if source_type == "csv":
            results = await import_csv_file(
                rag,
                csv_path=body.database_path,
                max_rows=body.max_rows_per_table,
                language=body.language,
                file_source_prefix=body.file_source_prefix,
                chunking=body.chunking,
                pipeline_index_texts=pipeline_index_texts,
                normalize_file_path=normalize_file_path,
                get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
                get_doc_status_value=get_doc_status_value,
                generate_track_id=generate_track_id,
                working_dir=rag.working_dir,
                csv_delimiter=body.csv_delimiter,
                dataset_name=body.dataset_name,
            )
            return results, "csv"

        from lightrag.api.sqlite_import_service import import_sqlite_tables

        results = await import_sqlite_tables(
            rag,
            database_path=body.database_path,
            tables=body.tables,
            max_rows_per_table=body.max_rows_per_table,
            language=body.language,
            file_source_prefix=body.file_source_prefix,
            chunking=body.chunking,
            pipeline_index_texts=pipeline_index_texts,
            normalize_file_path=normalize_file_path,
            get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
            get_doc_status_value=get_doc_status_value,
            generate_track_id=generate_track_id,
            working_dir=rag.working_dir,
            resolve_cross_table_links=body.resolve_cross_table_links,
        )
        return results, "sqlite"

    async def _run_import_sync_json(
        rag: LightRAG,
        body: SqliteImportRequest,
    ) -> tuple[list[SqliteTableConversionResult], Literal["sqlite", "csv"]]:
        source_type = _resolve_request_source_type(body)
        if source_type == "csv":
            results = await import_csv_file_as_json(
                rag,
                csv_path=body.database_path,
                max_rows=body.max_rows_per_table,
                file_source_prefix=body.file_source_prefix,
                normalize_file_path=normalize_file_path,
                get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
                get_doc_status_value=get_doc_status_value,
                generate_track_id=generate_track_id,
                working_dir=rag.working_dir,
                csv_delimiter=body.csv_delimiter,
                dataset_name=body.dataset_name,
            )
            return results, "csv"

        results = await import_sqlite_tables_as_json(
            rag,
            database_path=body.database_path,
            tables=body.tables,
            max_rows_per_table=body.max_rows_per_table,
            file_source_prefix=body.file_source_prefix,
            normalize_file_path=normalize_file_path,
            get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
            get_doc_status_value=get_doc_status_value,
            generate_track_id=generate_track_id,
            working_dir=rag.working_dir,
            resolve_cross_table_links=body.resolve_cross_table_links,
        )
        return results, "sqlite"

    async def _run_sqlite_import(
        rag: LightRAG,
        body: SqliteImportRequest,
    ) -> list[SqliteTableConversionResult]:
        results, _source_type = await _run_import_sync(rag, body)
        return results

    @router.post(
        "/import",
        response_model=SqliteImportJobResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def import_from_sqlite(
        http_request: Request,
        body: SqliteImportRequest,
        background_tasks: BackgroundTasks,
    ):
        """
        Read SQLite tables, convert each table to natural language via LLM, and
        enqueue documents through the same pipeline as ``POST /documents/text``.

        Each table becomes one document (one ``file_source`` / ``track_id``).
        Processing continues in the background; poll
        ``GET /documents/track_status/{track_id}`` or ``GET /documents/pipeline_status``.
        For per-table ``track_id`` values, use ``POST /sqlite/import_sync``.
        """
        rag = await _resolve(http_request)
        slot_reserved = False
        try:
            models_ok, probe_reason = await probe_import_models(rag)
            if not models_ok:
                slot_reserved = await _reserve_enqueue_slot(rag)

                async def _background_json_import():
                    try:
                        await _run_import_sync_json(rag, body)
                    except Exception as exc:
                        logger.error(
                            "[sqlite_import] Background JSON-deferred job failed: %s",
                            exc,
                            exc_info=True,
                        )
                    finally:
                        await _release_enqueue_slot(rag)

                background_tasks.add_task(_background_json_import)
                slot_reserved = False
                db_path = resolve_sqlite_database_path(
                    body.database_path, working_dir=rag.working_dir
                )
                target_tables = body.tables or list_sqlite_tables(db_path)
                import_job_id = generate_track_id("sqlite_json_job")
                return SqliteImportJobResponse(
                    status="started",
                    message=(
                        "LLM or embedding unavailable; exporting SQLite tables as JSON "
                        f"documents ({probe_reason}). Poll document list for incomplete "
                        "entries, then re-run import after models are enabled."
                    ),
                    job_id=import_job_id,
                    database_path=str(db_path),
                    tables=target_tables,
                )

            slot_reserved = await _reserve_enqueue_slot(rag)

            if body.chunking is not None:
                try:
                    _resolve_text_chunking(body.chunking, rag)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

            db_path = resolve_sqlite_database_path(
                body.database_path, working_dir=rag.working_dir
            )
            target_tables = body.tables or list_sqlite_tables(db_path)
            import_job_id = generate_track_id("sqlite_job")

            async def _background_import():
                try:
                    await _run_sqlite_import(
                        rag,
                        SqliteImportRequest(
                            database_path=str(db_path),
                            tables=body.tables,
                            max_rows_per_table=body.max_rows_per_table,
                            language=body.language,
                            file_source_prefix=body.file_source_prefix,
                            chunking=body.chunking,
                            resolve_cross_table_links=body.resolve_cross_table_links,
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "[sqlite_import] Background job %s failed: %s",
                        import_job_id,
                        exc,
                        exc_info=True,
                    )
                finally:
                    await _release_enqueue_slot(rag)

            background_tasks.add_task(_background_import)
            slot_reserved = False

            return SqliteImportJobResponse(
                status="started",
                message=(
                    "SQLite import started in background. Each table is converted "
                    "to natural language and enqueued via the /documents/text pipeline."
                ),
                job_id=import_job_id,
                database_path=str(db_path),
                tables=target_tables,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Error /sqlite/import: %s", exc, exc_info=True)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if slot_reserved:
                await _release_enqueue_slot(rag)

    @router.post(
        "/import_sync",
        response_model=SqliteImportResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def import_from_sqlite_sync(http_request: Request):
        """
        Synchronous variant of ``/sqlite/import`` — waits until all tables are
        converted and enqueued. Useful for scripts; may take a long time.

        Accepts either JSON (``database_path`` on the server) or
        ``multipart/form-data`` with a ``file`` field for remote SQLite or CSV uploads.
        CSV files are converted to natural language via LLM before indexing.

        When LLM or embedding is unavailable, tables are exported as JSON documents
        (``*.json`` file sources) and appear in the document list as incomplete.
        """
        rag = await _resolve(http_request)
        slot_reserved = False
        try:
            body = await _parse_import_sync_request(http_request, rag)
            source_type = _resolve_request_source_type(body)
            models_unavailable_reason: str | None = None
            if source_type in ("sqlite", "csv"):
                models_ok, probe_reason = await probe_import_models(rag)
                if not models_ok:
                    models_unavailable_reason = probe_reason or "unknown"
                    logger.warning(
                        "[sqlite_import] import_sync JSON-deferred (models unavailable): %s",
                        models_unavailable_reason,
                    )
                    slot_reserved = await _reserve_enqueue_slot(rag)
                    results, source_type = await _run_import_sync_json(rag, body)
                    if not any(r.status == "json_queued" for r in results):
                        return _build_upload_only_response(
                            body,
                            working_dir=rag.working_dir,
                            source_type=source_type,
                            reason=models_unavailable_reason,
                        )
                    return _build_import_sync_response(
                        body,
                        results,
                        working_dir=rag.working_dir,
                        source_type=source_type,
                        models_unavailable_reason=models_unavailable_reason,
                    )
            slot_reserved = await _reserve_enqueue_slot(rag)
            results, source_type = await _run_import_sync(rag, body)
            return _build_import_sync_response(
                body, results, working_dir=rag.working_dir, source_type=source_type
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Error /sqlite/import_sync: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if slot_reserved:
                await _release_enqueue_slot(rag)

    @router.post(
        "/table/upload",
        response_model=SqliteTableUploadResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def upload_sqlite_table(http_request: Request, body: SqliteTableUploadRequest):
        """
        将 SQLite 库中的**单张新表**导入当前任务空间：读取表数据 → LLM 转自然语言 →
        写入知识图谱（与 ``/sqlite/import_sync`` 单表逻辑相同）。

        须通过 ``LIGHTRAG-WORKSPACE`` 请求头指定任务空间，且与 body 中
        ``task_space_id`` 一致。
        """
        task_space_id = _validate_task_space_id(http_request, body.task_space_id)
        _validate_table_target(body)
        rag = await _resolve(http_request)
        slot_reserved = False
        destructive_acquired = False
        try:
            db_path = resolve_sqlite_database_path(
                body.database_path, working_dir=rag.working_dir
            )
            resolved_table = resolve_sqlite_table_reference(
                db_path,
                table_name=body.table_name,
                table_id=body.table_id,
            )

            if body.replace_if_exists:
                acquired, reason = await _acquire_destructive_busy(rag)
                if not acquired:
                    return SqliteTableUploadResponse(
                        status="failure",
                        message=reason or "Pipeline is busy; retry later",
                        task_space_id=task_space_id,
                        database_path=str(db_path),
                        table=resolved_table,
                        file_source="",
                        error="pipeline_busy",
                    )
                destructive_acquired = True
                await delete_sqlite_table_document(
                    rag,
                    database_path=str(db_path),
                    table_name=resolved_table,
                    file_source_prefix=body.file_source_prefix,
                    normalize_file_path=normalize_file_path,
                    get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
                    working_dir=rag.working_dir,
                )
                await _release_destructive_busy(rag)
                destructive_acquired = False

            slot_reserved = await _reserve_enqueue_slot(rag)
            results = await _run_sqlite_import(
                rag,
                SqliteImportRequest(
                    database_path=str(db_path),
                    tables=[resolved_table],
                    max_rows_per_table=body.max_rows_per_table,
                    language=body.language,
                    file_source_prefix=body.file_source_prefix,
                    chunking=body.chunking,
                    resolve_cross_table_links=body.resolve_cross_table_links,
                ),
            )
            item = results[0]
            response = _to_response_result(item)
            status_map = {
                "queued": "success",
                "skipped": "skipped",
                "failed": "failure",
            }
            return SqliteTableUploadResponse(
                status=status_map.get(response.status, "failure"),  # type: ignore[arg-type]
                message=(
                    f"Table '{resolved_table}' queued for indexing"
                    if response.status == "queued"
                    else (response.error or f"Table '{resolved_table}' was not imported")
                ),
                task_space_id=task_space_id,
                database_path=str(db_path),
                table=resolved_table,
                file_source=response.file_source,
                track_id=response.track_id,
                row_count=response.row_count,
                text_chars=response.text_chars,
                error=response.error,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Error /sqlite/table/upload: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if slot_reserved:
                await _release_enqueue_slot(rag)
            if destructive_acquired:
                await _release_destructive_busy(rag)

    @router.post(
        "/table/delete",
        response_model=SqliteTableDeleteResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def delete_sqlite_table(http_request: Request, body: SqliteTableDeleteRequest):
        """
        删除 SQLite 某张表在 LightRAG 中对应的文档、向量与知识图谱数据。

        根据 ``database_path`` + ``table_name``/``table_id`` 定位导入时生成的
        ``file_source``（如 ``sqlite_military-task_pilot.txt``）。
        """
        task_space_id = _validate_task_space_id(http_request, body.task_space_id)
        _validate_table_target(body)
        rag = await _resolve(http_request)
        acquired = False
        try:
            db_path = resolve_sqlite_database_path(
                body.database_path, working_dir=rag.working_dir
            )
            acquired, reason = await _acquire_destructive_busy(rag)
            if not acquired:
                return SqliteTableDeleteResponse(
                    status="busy",
                    message=reason or "Pipeline is busy; retry later",
                    task_space_id=task_space_id,
                    database_path=str(db_path),
                    table=body.table_name or body.table_id or "",
                    file_source="",
                    error="pipeline_busy",
                )

            result = await delete_sqlite_table_document(
                rag,
                database_path=str(db_path),
                table_name=body.table_name,
                table_id=body.table_id,
                file_source_prefix=body.file_source_prefix,
                normalize_file_path=normalize_file_path,
                get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
                working_dir=rag.working_dir,
                delete_llm_cache=body.delete_llm_cache,
            )
            return SqliteTableDeleteResponse(
                status=result.status,  # type: ignore[arg-type]
                message=result.message,
                task_space_id=task_space_id,
                database_path=str(db_path),
                table=result.table,
                file_source=result.file_source,
                doc_id=result.doc_id,
                error=result.error,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Error /sqlite/table/delete: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if acquired:
                await _release_destructive_busy(rag)

    return router
