"""
Read SQLite tables, convert each table to natural language via LLM, and enqueue
for the standard document ingestion pipeline (same path as ``/documents/text``).
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Literal

import aiofiles

from lightrag import LightRAG
from lightrag.sqlite_import_context import table_display_label
from lightrag.utils import get_env_value, logger, remove_think_tags
from lightrag.utils_pipeline import SQLITE_JSON_DEFERRED_MODE

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_SQLITE_TABLE_TO_TEXT_SYSTEM_PROMPT = """---Role---
You are a data narrator that converts structured database records into clear natural language.

---Instructions---
1. Write in {language}.
2. Preserve every factual field from the input (names, numbers, dates, IDs, relationships).
3. When ``__foreign_key_links`` or ``__*_entity_ref`` fields are present, always refer to the
   linked entity by its canonical display name (e.g. 张磊), not by bare numeric IDs alone.
4. The same person/entity must keep the same name across all tables — never create separate
   entities for an ID and its resolved name.
5. Use complete sentences and short paragraphs; group related rows logically.
6. Do not invent data that is not present in the input.
7. Output plain natural language only — no markdown code fences, no JSON.
8. **Opening format (required):** start with exactly this pattern:
   「{{表中文名}}包含{{N}}条记录，」then continue with the record narratives.
   Example: 飞行员表包含10条记录，张磊（上校）隶属于东部战区某歼击航空旅……
9. **Do NOT** describe table schema metadata — no sentences about primary-key columns,
   foreign-key columns, column lists, or which tables a column references.
10. Express relationships through entity names in the narrative (e.g. 飞行员张磊、所属单位东部战区某歼击航空旅),
    not through schema commentary.
11. When a ``---Cross-table Entity Registry---`` block is provided, use it only as background
    to resolve IDs to canonical names — do not copy the registry verbatim into the output.
"""

DEFAULT_CSV_TO_TEXT_SYSTEM_PROMPT = """---Role---
You are a data narrator that converts CSV/tabular records into clear natural language.

---Instructions---
1. Write in {language}.
2. Preserve every factual field from the input (names, numbers, dates, IDs, categories).
3. Use complete sentences and short paragraphs; group related rows logically.
4. Do not invent data that is not present in the input.
5. Output plain natural language only — no markdown code fences, no JSON.
6. **Opening format (required):** start with exactly this pattern:
   「{{dataset_label}}包含{{N}}条记录，」then continue with the record narratives.
7. **Do NOT** describe column schema metadata — no sentences listing column names,
   data types, or CSV structure.
8. Express each row as readable facts (who, what, when, where, values), not as key-value dumps.
"""

CROSS_TABLE_REGISTRY_SYSTEM_PROMPT = """---Role---
You are a knowledge-base indexer that writes a cross-table entity registry.

---Instructions---
1. Write in {language}.
2. List **every** entity with its primary key and canonical display name — do not omit any row.
3. Explicitly state that IDs appearing in other tables refer to the same entity.
4. For each table, write one sentence per ID mapping (e.g. "pilot.pilot_id=1 对应飞行员张磊").
5. **Never** summarize with only id=1 examples; include pilot_id=2, pilot_id=3, and all other IDs.
6. Output plain natural language only — no markdown code fences, no JSON.
"""


@dataclass
class TableMeta:
    table: str
    columns: list[str]
    primary_key: str
    display_column: str | None


@dataclass
class SqliteTableSnapshot:
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


@dataclass
class CsvSnapshot:
    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool
    delimiter: str
    encoding: str


@dataclass
class SqliteTableConversionResult:
    table: str
    file_source: str
    track_id: str
    row_count: int
    text_chars: int
    status: str
    error: str | None = None


_SQLITE_UPLOAD_DIRNAME = "sqlite_uploads"
_SQLITE_JSON_DIRNAME = "sqlite_json"
_DEFAULT_SQLITE_UPLOAD_MAX_BYTES = 100 * 1024 * 1024


def sqlite_upload_max_bytes() -> int | None:
    """Max upload size in bytes; ``None`` means unlimited."""
    raw = get_env_value("SQLITE_UPLOAD_MAX_BYTES", str(_DEFAULT_SQLITE_UPLOAD_MAX_BYTES))
    if raw is None:
        return _DEFAULT_SQLITE_UPLOAD_MAX_BYTES
    text = str(raw).strip().lower()
    if text in {"", "0", "none", "null", "unlimited"}:
        return None
    return int(text)


def sqlite_upload_dir(working_dir: str) -> Path:
    path = Path(working_dir).expanduser().resolve() / _SQLITE_UPLOAD_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def sqlite_json_export_dir(working_dir: str) -> Path:
    path = Path(working_dir).expanduser().resolve() / _SQLITE_JSON_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_table_json_export_file(
    json_text: str,
    *,
    working_dir: str,
    db_path: Path,
    table: str,
) -> Path:
    dest_dir = sqlite_json_export_dir(working_dir) / db_path.stem
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{table}.json"
    async with aiofiles.open(dest, "w", encoding="utf-8") as handle:
        await handle.write(json_text)
    return dest


def default_json_file_source_for_table(
    db_path: Path,
    table: str,
    prefix: str | None = None,
) -> str:
    base = f"sqlite_{db_path.stem}_{table}.json"
    if prefix:
        cleaned = prefix.strip().rstrip("/")
        return f"{cleaned}/{base}"
    return base


def default_json_file_source_for_csv(
    csv_path: Path,
    prefix: str | None = None,
) -> str:
    base = f"csv_{csv_path.stem}.json"
    if prefix:
        cleaned = prefix.strip().rstrip("/")
        return f"{cleaned}/{base}"
    return base


async def _stamp_json_deferred_metadata(
    rag: LightRAG,
    *,
    file_sources: list[str],
    normalize_file_path,
    source_database_path: str | None = None,
    table_by_source: dict[str, str] | None = None,
) -> None:
    updates: dict[str, dict[str, Any]] = {}
    for file_source in file_sources:
        basename = normalize_file_path(file_source)
        match = await rag.doc_status.get_doc_by_file_basename(basename)
        if not match:
            continue
        doc_id, doc = match
        record = dict(doc) if isinstance(doc, dict) else doc.__dict__.copy()
        metadata = dict(record.get("metadata") or {})
        metadata["sqlite_import_mode"] = SQLITE_JSON_DEFERRED_MODE
        metadata["awaiting_models"] = True
        if source_database_path:
            metadata["source_database_path"] = source_database_path
        if table_by_source and file_source in table_by_source:
            metadata["source_table"] = table_by_source[file_source]
        record["metadata"] = metadata
        updates[doc_id] = record
    if updates:
        await rag.doc_status.upsert(updates)
        await rag.doc_status.index_done_callback()


async def enqueue_json_deferred_documents(
    rag: LightRAG,
    *,
    texts: list[str],
    file_sources: list[str],
    track_id: str,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    source_database_path: str | None = None,
    table_by_source: dict[str, str] | None = None,
) -> None:
    """Enqueue JSON table exports as PENDING docs without running the pipeline."""
    if not texts:
        return
    normalized_sources = [normalize_file_path(source) for source in file_sources]
    await rag.apipeline_enqueue_documents(
        input=texts,
        file_paths=normalized_sources,
        track_id=track_id,
    )
    await _stamp_json_deferred_metadata(
        rag,
        file_sources=normalized_sources,
        normalize_file_path=normalize_file_path,
        source_database_path=source_database_path,
        table_by_source=table_by_source,
    )


async def import_sqlite_tables_as_json(
    rag: LightRAG,
    *,
    database_path: str,
    tables: Iterable[str] | None,
    max_rows_per_table: int,
    file_source_prefix: str | None,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    get_doc_status_value,
    generate_track_id,
    working_dir: str | None = None,
    resolve_cross_table_links: bool = True,
) -> list[SqliteTableConversionResult]:
    """Export SQLite tables as JSON documents when LLM/embedding is unavailable."""
    db_path = resolve_sqlite_database_path(database_path, working_dir=working_dir)
    available_tables = list_sqlite_tables(db_path)
    if not available_tables:
        raise ValueError(f"No user tables found in database: {db_path}")

    if tables:
        requested = [_validate_table_name(t) for t in tables]
        missing = sorted(set(requested) - set(available_tables))
        if missing:
            raise ValueError(
                f"Unknown table(s): {', '.join(missing)}. "
                f"Available: {', '.join(available_tables)}"
            )
        target_tables = requested
    else:
        target_tables = available_tables

    snapshots: dict[str, SqliteTableSnapshot] = {}
    for table in target_tables:
        snapshots[table] = fetch_sqlite_table_snapshot(
            db_path, table, max_rows=max_rows_per_table
        )

    registry: dict[str, dict[Any, dict[str, Any]]] = {}
    meta: dict[str, TableMeta] = {}
    pk_by_table: dict[str, str] = {}
    if resolve_cross_table_links:
        registry, meta = build_entity_registry(db_path, snapshots)
        pk_by_table = {table: table_meta.primary_key for table, table_meta in meta.items()}
        target_tables = sort_tables_by_foreign_key_dependencies(
            target_tables,
            snapshots,
            pk_by_table,
        )

    results: list[SqliteTableConversionResult] = []
    batch_texts: list[str] = []
    batch_sources: list[str] = []
    table_by_source: dict[str, str] = {}
    batch_track_id = generate_track_id("sqlite_json")

    for table in target_tables:
        file_source = default_json_file_source_for_table(
            db_path, table, file_source_prefix
        )
        normalized_source = normalize_file_path(file_source)
        track_id = generate_track_id("sqlite_json")

        try:
            snapshot = snapshots[table]
            if not snapshot.rows:
                results.append(
                    SqliteTableConversionResult(
                        table=table,
                        file_source=normalized_source,
                        track_id=track_id,
                        row_count=0,
                        text_chars=0,
                        status="skipped",
                        error="Table is empty",
                    )
                )
                continue

            existing_doc = await get_existing_doc_by_file_path_candidates(
                rag.doc_status, normalized_source
            )
            if existing_doc:
                status = get_doc_status_value(existing_doc) or "unknown"
                results.append(
                    SqliteTableConversionResult(
                        table=table,
                        file_source=normalized_source,
                        track_id=track_id,
                        row_count=0,
                        text_chars=0,
                        status="skipped",
                        error=(
                            f"Document already exists for '{normalized_source}' "
                            f"(status={status}). Delete it before re-importing."
                        ),
                    )
                )
                continue

            json_text = build_table_prompt_payload(
                snapshot,
                registry=registry if resolve_cross_table_links else None,
                meta=meta if resolve_cross_table_links else None,
                pk_by_table=pk_by_table if resolve_cross_table_links else None,
            )
            if working_dir:
                await save_table_json_export_file(
                    json_text,
                    working_dir=working_dir,
                    db_path=db_path,
                    table=table,
                )

            batch_texts.append(json_text)
            batch_sources.append(normalized_source)
            table_by_source[normalized_source] = table
            results.append(
                SqliteTableConversionResult(
                    table=table,
                    file_source=normalized_source,
                    track_id=batch_track_id,
                    row_count=len(snapshot.rows),
                    text_chars=len(json_text),
                    status="json_queued",
                )
            )
            logger.info(
                "[sqlite_import] JSON-deferred table '%s' (%s rows, %s chars)",
                table,
                len(snapshot.rows),
                len(json_text),
            )
        except Exception as exc:
            logger.error(
                "[sqlite_import] JSON export failed for table '%s': %s",
                table,
                exc,
                exc_info=True,
            )
            results.append(
                SqliteTableConversionResult(
                    table=table,
                    file_source=normalized_source,
                    track_id=track_id,
                    row_count=0,
                    text_chars=0,
                    status="failed",
                    error=str(exc),
                )
            )

    if batch_texts:
        await enqueue_json_deferred_documents(
            rag,
            texts=batch_texts,
            file_sources=batch_sources,
            track_id=batch_track_id,
            normalize_file_path=normalize_file_path,
            get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
            source_database_path=str(db_path),
            table_by_source=table_by_source,
        )

    return results


async def import_csv_file_as_json(
    rag: LightRAG,
    *,
    csv_path: str,
    max_rows: int,
    file_source_prefix: str | None,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    get_doc_status_value,
    generate_track_id,
    working_dir: str | None = None,
    csv_delimiter: str | None = None,
    dataset_name: str | None = None,
) -> list[SqliteTableConversionResult]:
    """Export a CSV dataset as a JSON document when LLM/embedding is unavailable."""
    path = resolve_csv_file_path(csv_path, working_dir=working_dir)
    snapshot = read_csv_snapshot(
        path,
        max_rows=max_rows,
        delimiter=csv_delimiter,
        dataset_name=dataset_name,
    )
    file_source = default_json_file_source_for_csv(path, file_source_prefix)
    normalized_source = normalize_file_path(file_source)
    track_id = generate_track_id("csv_json")
    table_label = snapshot.name

    if not snapshot.rows:
        return [
            SqliteTableConversionResult(
                table=table_label,
                file_source=normalized_source,
                track_id=track_id,
                row_count=0,
                text_chars=0,
                status="skipped",
                error="CSV has no data rows",
            )
        ]

    existing_doc = await get_existing_doc_by_file_path_candidates(
        rag.doc_status, normalized_source
    )
    if existing_doc:
        status = get_doc_status_value(existing_doc) or "unknown"
        return [
            SqliteTableConversionResult(
                table=table_label,
                file_source=normalized_source,
                track_id=track_id,
                row_count=0,
                text_chars=0,
                status="skipped",
                error=(
                    f"Document already exists for '{normalized_source}' "
                    f"(status={status}). Delete it before re-importing."
                ),
            )
        ]

    json_text = build_csv_prompt_payload(snapshot)
    if working_dir:
        dest_dir = sqlite_json_export_dir(working_dir) / path.stem
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{snapshot.name}.json"
        async with aiofiles.open(dest, "w", encoding="utf-8") as handle:
            await handle.write(json_text)

    await enqueue_json_deferred_documents(
        rag,
        texts=[json_text],
        file_sources=[normalized_source],
        track_id=track_id,
        normalize_file_path=normalize_file_path,
        get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
        source_database_path=str(path),
        table_by_source={normalized_source: table_label},
    )
    return [
        SqliteTableConversionResult(
            table=table_label,
            file_source=normalized_source,
            track_id=track_id,
            row_count=len(snapshot.rows),
            text_chars=len(json_text),
            status="json_queued",
        )
    ]


_MODEL_PROBE_TEXT = "ping"


def import_model_probe_timeout_sec() -> float:
    raw = get_env_value("SQLITE_IMPORT_PROBE_TIMEOUT_SEC", "20")
    return float(raw)


def import_llm_enabled() -> bool:
    """Whether LLM may be used for SQLite/CSV import (see LIGHTRAG_LLM_ENABLED)."""
    return get_env_value("LIGHTRAG_LLM_ENABLED", True, bool)


def import_embedding_enabled() -> bool:
    """Whether embedding may be used for SQLite/CSV import (see LIGHTRAG_EMBEDDING_ENABLED)."""
    return get_env_value("LIGHTRAG_EMBEDDING_ENABLED", True, bool)


async def probe_import_models(
    rag: LightRAG,
    *,
    timeout_sec: float | None = None,
) -> tuple[bool, str | None]:
    """Check whether LLM and embedding backends are enabled and respond before import."""
    if not import_llm_enabled():
        return False, "LLM disabled (LIGHTRAG_LLM_ENABLED=false)"
    if not import_embedding_enabled():
        return False, "Embedding disabled (LIGHTRAG_EMBEDDING_ENABLED=false)"

    timeout = import_model_probe_timeout_sec() if timeout_sec is None else timeout_sec

    llm_func = rag.role_llm_funcs.get("query") or rag.llm_model_func
    if llm_func is None:
        return False, "No LLM function configured"

    if rag.embedding_func is None:
        return False, "No embedding function configured"

    async def _probe_llm() -> None:
        response = await llm_func(
            _MODEL_PROBE_TEXT,
            system_prompt="Reply with exactly: ok",
        )
        if response is None or (isinstance(response, str) and not response.strip()):
            raise RuntimeError("LLM returned empty response")

    async def _probe_embedding() -> None:
        vectors = await rag.embedding_func([_MODEL_PROBE_TEXT])
        if vectors is None:
            raise RuntimeError("Embedding returned None")
        try:
            if len(vectors) < 1:
                raise RuntimeError("Embedding returned empty result")
        except TypeError:
            pass

    try:
        await asyncio.wait_for(_probe_llm(), timeout=timeout)
    except asyncio.TimeoutError:
        return False, "LLM probe timed out"
    except Exception as exc:
        return False, f"LLM unavailable: {exc}"

    try:
        await asyncio.wait_for(_probe_embedding(), timeout=timeout)
    except asyncio.TimeoutError:
        return False, "Embedding probe timed out"
    except Exception as exc:
        return False, f"Embedding unavailable: {exc}"

    return True, None


def _is_working_dir_sqlite_upload(candidate: Path, working_dir: str | None) -> bool:
    if not working_dir:
        return False
    upload_root = sqlite_upload_dir(working_dir)
    try:
        candidate.resolve().relative_to(upload_root)
        return True
    except ValueError:
        return False


def parse_sqlite_import_tables_form(raw: str | None) -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("tables must be a JSON array of table names")
        tables = [str(item).strip() for item in parsed if str(item).strip()]
        return tables or None
    tables = [part.strip() for part in text.split(",") if part.strip()]
    return tables or None


def parse_sqlite_import_bool_form(raw: str | None, *, default: bool = True) -> bool:
    if raw is None or not str(raw).strip():
        return default
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean form value: {raw!r}")


def _safe_import_upload_filename(
    original: str | None,
    *,
    default_name: str,
    allowed_suffixes: tuple[str, ...],
    fallback_suffix: str,
) -> str:
    name = Path(original or default_name).name
    if name in {"", ".", ".."}:
        name = default_name
    safe = re.sub(r"[^\w.\-]", "_", name)
    lower = safe.lower()
    for suffix in allowed_suffixes:
        if lower.endswith(suffix):
            stem = safe[: -len(suffix)] or "upload"
            return f"{uuid.uuid4().hex}_{stem}{suffix}"
    return f"{uuid.uuid4().hex}_{safe}{fallback_suffix}"


def _safe_sqlite_upload_filename(original: str | None) -> str:
    return _safe_import_upload_filename(
        original,
        default_name="upload.db",
        allowed_suffixes=(".db", ".sqlite", ".sqlite3"),
        fallback_suffix=".db",
    )


def _safe_csv_upload_filename(original: str | None) -> str:
    return _safe_import_upload_filename(
        original,
        default_name="upload.csv",
        allowed_suffixes=(".csv", ".tsv", ".txt"),
        fallback_suffix=".csv",
    )


def is_csv_import_path(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".csv", ".tsv", ".txt"}


def is_sqlite_import_path(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".db", ".sqlite", ".sqlite3"}


def detect_import_source_type(path: str | Path) -> Literal["sqlite", "csv"]:
    if is_csv_import_path(path):
        return "csv"
    if is_sqlite_import_path(path):
        return "sqlite"
    raise ValueError(
        "Unsupported import file type; upload .db/.sqlite/.sqlite3 or .csv/.tsv"
    )


async def _save_uploaded_import_file(
    upload_file,
    *,
    working_dir: str,
    dest_filename: str,
    empty_error: str,
    size_error_label: str,
) -> Path:
    """Persist a multipart upload under ``{working_dir}/sqlite_uploads/``."""
    dest_dir = sqlite_upload_dir(working_dir)
    dest_path = dest_dir / dest_filename
    max_bytes = sqlite_upload_max_bytes()
    chunk_size = 1024 * 1024
    bytes_written = 0

    async with aiofiles.open(dest_path, "wb") as out_file:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            if max_bytes is not None:
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    await out_file.close()
                    dest_path.unlink(missing_ok=True)
                    limit_mb = max_bytes / 1024 / 1024
                    uploaded_mb = bytes_written / 1024 / 1024
                    raise ValueError(
                        f"Uploaded {size_error_label} file exceeds SQLITE_UPLOAD_MAX_BYTES "
                        f"({limit_mb:.1f}MB, received {uploaded_mb:.1f}MB)"
                    )
            await out_file.write(chunk)

    if bytes_written == 0:
        dest_path.unlink(missing_ok=True)
        raise ValueError(empty_error)

    return dest_path.resolve()


async def save_uploaded_sqlite_database(
    upload_file,
    *,
    working_dir: str,
    original_filename: str | None = None,
) -> Path:
    return await _save_uploaded_import_file(
        upload_file,
        working_dir=working_dir,
        dest_filename=_safe_sqlite_upload_filename(original_filename),
        empty_error="Uploaded SQLite file is empty",
        size_error_label="SQLite",
    )


async def save_uploaded_csv_file(
    upload_file,
    *,
    working_dir: str,
    original_filename: str | None = None,
) -> Path:
    return await _save_uploaded_import_file(
        upload_file,
        working_dir=working_dir,
        dest_filename=_safe_csv_upload_filename(original_filename),
        empty_error="Uploaded CSV file is empty",
        size_error_label="CSV",
    )


def _allowed_sqlite_roots() -> list[Path]:
    raw = get_env_value("SQLITE_IMPORT_ALLOWED_DIRS", "")
    roots: list[Path] = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if part:
                roots.append(Path(part).expanduser().resolve())
    return roots


def resolve_sqlite_database_path(database_path: str, *, working_dir: str | None = None) -> Path:
    """Resolve and validate a SQLite database path against allowed roots."""
    if not database_path or not database_path.strip():
        raise ValueError("database_path is required")

    candidate = Path(database_path.strip()).expanduser()
    if not candidate.is_absolute():
        base = Path(working_dir or ".").expanduser().resolve()
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError(
            "database_path must point to a SQLite file (.db, .sqlite, .sqlite3)"
        )
    if not candidate.is_file():
        raise ValueError(f"SQLite database not found: {candidate}")

    if _is_working_dir_sqlite_upload(candidate, working_dir):
        return candidate

    allowed_roots = _allowed_sqlite_roots()
    if allowed_roots:
        if not any(
            candidate == root or root in candidate.parents for root in allowed_roots
        ):
            raise ValueError(
                "database_path is outside SQLITE_IMPORT_ALLOWED_DIRS; "
                f"allowed roots: {', '.join(str(r) for r in allowed_roots)}"
            )

    return candidate


def resolve_csv_file_path(csv_path: str, *, working_dir: str | None = None) -> Path:
    """Resolve and validate a CSV file path against allowed roots."""
    if not csv_path or not csv_path.strip():
        raise ValueError("csv_path is required")

    candidate = Path(csv_path.strip()).expanduser()
    if not candidate.is_absolute():
        base = Path(working_dir or ".").expanduser().resolve()
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not is_csv_import_path(candidate):
        raise ValueError("csv_path must point to a CSV file (.csv, .tsv, .txt)")
    if not candidate.is_file():
        raise ValueError(f"CSV file not found: {candidate}")

    if _is_working_dir_sqlite_upload(candidate, working_dir):
        return candidate

    allowed_roots = _allowed_sqlite_roots()
    if allowed_roots:
        if not any(
            candidate == root or root in candidate.parents for root in allowed_roots
        ):
            raise ValueError(
                "csv_path is outside SQLITE_IMPORT_ALLOWED_DIRS; "
                f"allowed roots: {', '.join(str(r) for r in allowed_roots)}"
            )

    return candidate


def resolve_import_source_path(
    source_path: str,
    *,
    working_dir: str | None = None,
) -> tuple[Path, Literal["sqlite", "csv"]]:
    source_type = detect_import_source_type(source_path)
    if source_type == "csv":
        return resolve_csv_file_path(source_path, working_dir=working_dir), "csv"
    return resolve_sqlite_database_path(source_path, working_dir=working_dir), "sqlite"


def _decode_csv_text(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode CSV file; use UTF-8 or GBK encoding")


def _detect_csv_delimiter(text: str, *, explicit: str | None = None) -> str:
    if explicit:
        if explicit.lower() in {"tab", "\\t"}:
            return "\t"
        if explicit.lower() == "comma":
            return ","
        if explicit.lower() == "semicolon":
            return ";"
        if len(explicit) == 1:
            return explicit
        raise ValueError(f"Invalid csv_delimiter: {explicit!r}")

    sample = text[:8192]
    if not sample.strip():
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        if "\t" in sample.splitlines()[0]:
            return "\t"
        return ","


def read_csv_snapshot(
    csv_path: Path,
    *,
    max_rows: int,
    delimiter: str | None = None,
    dataset_name: str | None = None,
) -> CsvSnapshot:
    raw = csv_path.read_bytes()
    text, encoding = _decode_csv_text(raw)
    if not text.strip():
        raise ValueError(f"CSV file is empty: {csv_path}")

    delim = _detect_csv_delimiter(text, explicit=delimiter)
    reader = csv.DictReader(StringIO(text), delimiter=delim)
    if not reader.fieldnames:
        raise ValueError(f"CSV file has no header row: {csv_path}")

    columns = [str(name).strip() for name in reader.fieldnames if name is not None]
    if not columns:
        raise ValueError(f"CSV file has no usable columns: {csv_path}")

    limit = max(1, max_rows)
    rows: list[dict[str, Any]] = []
    total = 0
    for row in reader:
        total += 1
        if len(rows) >= limit:
            continue
        normalized: dict[str, Any] = {}
        for col in columns:
            value = row.get(col)
            normalized[col] = None if value in (None, "") else value
        rows.append(normalized)

    name = dataset_name or csv_path.stem
    return CsvSnapshot(
        name=name,
        columns=columns,
        rows=rows,
        truncated=total > len(rows),
        delimiter=delim,
        encoding=encoding,
    )


def build_csv_prompt_payload(snapshot: CsvSnapshot) -> str:
    payload = {
        "dataset": snapshot.name,
        "columns": snapshot.columns,
        "row_count": len(snapshot.rows),
        "truncated": snapshot.truncated,
        "rows": snapshot.rows,
    }
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def default_file_source_for_csv(
    csv_path: Path,
    prefix: str | None = None,
) -> str:
    base = f"csv_{csv_path.stem}.txt"
    if prefix:
        cleaned = prefix.strip().rstrip("/")
        return f"{cleaned}/{base}"
    return base


def _validate_table_name(table: str) -> str:
    name = table.strip()
    if not name or not _TABLE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid table name '{table}'; use letters, digits, and underscores only"
        )
    return name


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_sqlite_tables(db_path: Path) -> list[str]:
    with _connect_readonly(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]


def fetch_sqlite_table_snapshot(
    db_path: Path,
    table: str,
    *,
    max_rows: int,
) -> SqliteTableSnapshot:
    table_name = _validate_table_name(table)
    with _connect_readonly(db_path) as conn:
        columns = [
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name!r})").fetchall()
        ]
        if not columns:
            raise ValueError(f"Table '{table_name}' has no columns or does not exist")

        total = conn.execute(f"SELECT COUNT(*) FROM {table_name!r}").fetchone()[0]
        limit = max(1, max_rows)
        rows_cursor = conn.execute(
            f"SELECT * FROM {table_name!r} LIMIT ?",
            (limit,),
        )
        rows = [dict(row) for row in rows_cursor.fetchall()]

    return SqliteTableSnapshot(
        table=table_name,
        columns=columns,
        rows=rows,
        truncated=total > len(rows),
    )


def get_table_primary_key(db_path: Path, table: str, columns: list[str]) -> str:
    table_name = _validate_table_name(table)
    with _connect_readonly(db_path) as conn:
        info = conn.execute(f"PRAGMA table_info({table_name!r})").fetchall()
    pk_cols = [row[1] for row in info if row[5]]
    if len(pk_cols) == 1:
        return pk_cols[0]

    for candidate in (f"{table_name}_id", "id", f"{table_name.rstrip('s')}_id"):
        if candidate in columns:
            return candidate
    return columns[0]


def detect_display_column(columns: list[str], table: str) -> str | None:
    singular = table.rstrip("s") if table.endswith("s") else table
    candidates = [
        f"{singular}_name",
        f"{table}_name",
        "name",
        "title",
        "label",
        "code",
        "tail_number",
    ]
    for candidate in candidates:
        if candidate in columns:
            return candidate
    for column in columns:
        if column.endswith("_name"):
            return column
    return None


def _fk_column_stem(column: str) -> str:
    """Entity stem from a ``*_id`` column (``pilot_id`` -> ``pilot``)."""
    return column[:-3]


def _pk_entity_stem(pk: str) -> str | None:
    """Entity stem from a non-generic PK (``pilot_id`` -> ``pilot``; ``id`` -> None)."""
    if pk == "id":
        return None
    if pk.endswith("_id"):
        return pk[:-3]
    return None


def _table_matches_entity_stem(table: str, stem: str) -> bool:
    """True when ``table`` is the master entity table for ``stem`` (not a child table)."""
    if not stem:
        return False
    if table == stem:
        return True
    table_singular = table[:-1] if table.endswith("s") and len(table) > 1 else table
    stem_singular = stem[:-1] if stem.endswith("s") and len(stem) > 1 else stem
    return table_singular == stem_singular


def _is_entity_master_pk(stem: str, pk: str) -> bool:
    """True when ``pk`` is the dedicated primary key for entity ``stem``."""
    if pk == f"{stem}_id":
        return True
    stem_singular = stem[:-1] if stem.endswith("s") and len(stem) > 1 else stem
    return pk == f"{stem_singular}_id"


def infer_foreign_key_target(
    column: str,
    pk_by_table: dict[str, str],
) -> tuple[str, str] | None:
    if not column.endswith("_id"):
        return None

    exact_matches = [(table, pk) for table, pk in pk_by_table.items() if pk == column]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        stem = _fk_column_stem(column)
        for table, pk in exact_matches:
            if table == stem or table.startswith(stem):
                return table, pk
        return exact_matches[0]

    stem = _fk_column_stem(column)
    if stem in pk_by_table and pk_by_table[stem] == column:
        return stem, column

    suffix_matches: list[tuple[str, str]] = []
    for table, pk in pk_by_table.items():
        if not column.endswith(f"_{pk}"):
            continue
        if pk == "id":
            # Do not map pilot_id -> arbitrary_table.id; require a master entity table.
            if _table_matches_entity_stem(table, stem):
                suffix_matches.append((table, pk))
            continue
        pk_stem = _pk_entity_stem(pk)
        if pk_stem is None:
            continue
        if not (_table_matches_entity_stem(table, pk_stem) or _is_entity_master_pk(pk_stem, pk)):
            continue
        if stem == pk_stem or stem.endswith(f"_{pk_stem}"):
            suffix_matches.append((table, pk))

    if not suffix_matches:
        return None
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    for table, pk in suffix_matches:
        if table == stem or table == f"{stem}s":
            return table, pk
    return suffix_matches[0]


def build_entity_registry(
    db_path: Path,
    snapshots: dict[str, SqliteTableSnapshot],
) -> tuple[dict[str, dict[Any, dict[str, Any]]], dict[str, TableMeta]]:
    registry: dict[str, dict[Any, dict[str, Any]]] = {}
    meta: dict[str, TableMeta] = {}

    for table, snapshot in snapshots.items():
        primary_key = get_table_primary_key(db_path, table, snapshot.columns)
        display_column = detect_display_column(snapshot.columns, table)
        meta[table] = TableMeta(
            table=table,
            columns=snapshot.columns,
            primary_key=primary_key,
            display_column=display_column,
        )
        table_rows: dict[Any, dict[str, Any]] = {}
        for row in snapshot.rows:
            if primary_key not in row:
                continue
            table_rows[row[primary_key]] = row
        registry[table] = table_rows

    return registry, meta


def get_entity_display_name(
    row: dict[str, Any],
    table_meta: TableMeta,
) -> str:
    if table_meta.display_column:
        value = row.get(table_meta.display_column)
        if value not in (None, ""):
            return str(value)
    return f"{table_meta.table}.{table_meta.primary_key}={row.get(table_meta.primary_key)}"


def enrich_row_with_foreign_keys(
    row: dict[str, Any],
    *,
    registry: dict[str, dict[Any, dict[str, Any]]],
    meta: dict[str, TableMeta],
    pk_by_table: dict[str, str],
) -> dict[str, Any]:
    enriched = dict(row)
    links: list[str] = []

    for column, value in row.items():
        if value is None:
            continue
        ref = infer_foreign_key_target(column, pk_by_table)
        if not ref:
            continue

        ref_table, ref_pk = ref
        ref_row = registry.get(ref_table, {}).get(value)
        if not ref_row:
            continue

        ref_meta = meta[ref_table]
        display_name = get_entity_display_name(ref_row, ref_meta)
        entity_ref = f"{display_name}({ref_table}.{ref_pk}={value})"
        enriched[f"__{column}_canonical_name"] = display_name
        enriched[f"__{column}_entity_ref"] = entity_ref
        links.append(
            f"{column}={value} 即 {ref_table}.{ref_meta.display_column or ref_pk}="
            f"{display_name}（同一实体：{display_name}）"
        )

    if links:
        enriched["__foreign_key_links"] = links
    return enriched


def build_cross_table_registry_text(
    registry: dict[str, dict[Any, dict[str, Any]]],
    meta: dict[str, TableMeta],
) -> str:
    lines = ["--- 跨表实体索引（不同表中的相同 ID 指向同一实体）---"]
    for table in sorted(registry):
        table_meta = meta[table]
        rows = registry[table]
        if not rows:
            continue
        lines.append(f"[{table}] 主键={table_meta.primary_key}")
        for pk_value in sorted(rows, key=lambda item: str(item)):
            row = rows[pk_value]
            display_name = get_entity_display_name(row, table_meta)
            lines.append(
                f"- {table}.{table_meta.primary_key}={pk_value} → {display_name}"
            )
    return "\n".join(lines)


def _table_display_label(table: str) -> str:
    return table_display_label(table)


def build_registry_document_text(
    registry: dict[str, dict[Any, dict[str, Any]]],
    meta: dict[str, TableMeta],
    *,
    snapshots: dict[str, SqliteTableSnapshot] | None = None,
    pk_by_table: dict[str, str] | None = None,
) -> str:
    """Deterministic registry document — full ID list, no LLM summarization."""
    lines = [
        "跨表实体索引（完整列表，不得省略任何 ID）",
        "",
        "规则：不同表中出现相同主键或外键 ID 时，指向同一现实世界实体。",
        "以下为每个表中全部 ID 与实体名称的一一对应，以及表与实体之间的包含关系。",
        "",
    ]

    for table in sorted(registry):
        table_meta = meta[table]
        rows = registry[table]
        if not rows:
            continue

        label = _table_display_label(table)
        lines.append(f"## {label}（{table}）")
        lines.append(f"主键字段：{table_meta.primary_key}")
        for pk_value in sorted(rows, key=lambda item: str(item)):
            row = rows[pk_value]
            display_name = get_entity_display_name(row, table_meta)
            lines.append(
                f"- {table}.{table_meta.primary_key}={pk_value} → {display_name}"
            )
            lines.append(
                f"  {label}通过{table_meta.primary_key}={pk_value}包含实体「{display_name}」。"
            )
            lines.append(
                f"  其他表中出现的 {table_meta.primary_key}={pk_value} 或引用该 ID 的外键，"
                f"均指同一实体「{display_name}」。"
            )
        lines.append("")

    if snapshots and pk_by_table:
        lines.append("## 外键字段说明")
        seen: set[str] = set()
        for table in sorted(snapshots):
            snapshot = snapshots[table]
            for column in snapshot.columns:
                ref = infer_foreign_key_target(column, pk_by_table)
                if not ref:
                    continue
                ref_table, ref_pk = ref
                key = f"{table}.{column}->{ref_table}.{ref_pk}"
                if key in seen:
                    continue
                seen.add(key)
                ref_label = _table_display_label(ref_table)
                lines.append(
                    f"- {table}.{column} 引用 {ref_table}.{ref_pk}；"
                    f"当 {table}.{column}=N 时，与 {ref_table}.{ref_pk}=N 表示同一"
                    f"{ref_label.replace('表', '')}实体。"
                )

    return "\n".join(lines).strip() + "\n"


def sort_tables_by_foreign_key_dependencies(
    tables: list[str],
    snapshots: dict[str, SqliteTableSnapshot],
    pk_by_table: dict[str, str],
) -> list[str]:
    dependencies: dict[str, set[str]] = {table: set() for table in tables}
    for table in tables:
        snapshot = snapshots[table]
        for column in snapshot.columns:
            ref = infer_foreign_key_target(column, pk_by_table)
            if ref and ref[0] in dependencies and ref[0] != table:
                dependencies[table].add(ref[0])

    ordered: list[str] = []
    pending = list(tables)
    while pending:
        ready = [table for table in pending if not dependencies[table] - set(ordered)]
        if not ready:
            ordered.extend(sorted(pending))
            break
        ready.sort()
        ordered.extend(ready)
        pending = [table for table in pending if table not in ready]
    return ordered


def build_table_prompt_payload(
    snapshot: SqliteTableSnapshot,
    *,
    registry: dict[str, dict[Any, dict[str, Any]]] | None = None,
    meta: dict[str, TableMeta] | None = None,
    pk_by_table: dict[str, str] | None = None,
) -> str:
    rows = snapshot.rows
    if registry and meta and pk_by_table:
        rows = [
            enrich_row_with_foreign_keys(
                row,
                registry=registry,
                meta=meta,
                pk_by_table=pk_by_table,
            )
            for row in snapshot.rows
        ]

    payload = {
        "table": snapshot.table,
        "columns": snapshot.columns,
        "row_count": len(rows),
        "truncated": snapshot.truncated,
        "rows": rows,
    }
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def default_file_source_for_table(db_path: Path, table: str, prefix: str | None = None) -> str:
    stem = db_path.stem
    base = f"sqlite_{stem}_{table}.txt"
    if prefix:
        cleaned = prefix.strip().rstrip("/")
        return f"{cleaned}/{base}"
    return base


async def convert_table_rows_to_natural_language(
    rag: LightRAG,
    *,
    snapshot: SqliteTableSnapshot,
    language: str,
    system_prompt_template: str | None = None,
    max_prompt_chars: int = 120_000,
    registry: dict[str, dict[Any, dict[str, Any]]] | None = None,
    meta: dict[str, TableMeta] | None = None,
    pk_by_table: dict[str, str] | None = None,
    cross_table_registry_text: str | None = None,
) -> str:
    llm_func = rag.role_llm_funcs.get("query") or rag.llm_model_func
    if llm_func is None:
        raise RuntimeError("No LLM function configured for natural-language conversion")

    system_prompt = (system_prompt_template or DEFAULT_SQLITE_TABLE_TO_TEXT_SYSTEM_PROMPT).format(
        language=language
    )
    payload = build_table_prompt_payload(
        snapshot,
        registry=registry,
        meta=meta,
        pk_by_table=pk_by_table,
    )
    if len(payload) > max_prompt_chars:
        payload = payload[:max_prompt_chars] + "\n... [truncated for LLM input limit]"

    registry_block = ""
    if cross_table_registry_text:
        registry_block = (
            "\n\n---Cross-table Entity Registry (guidance for ID resolution; "
            "do NOT copy verbatim into output)---\n"
            f"{cross_table_registry_text}\n"
        )

    table_label = _table_display_label(snapshot.table)
    row_count = len(snapshot.rows)

    user_prompt = (
        f"Convert the following SQLite table export into natural language.\n"
        f"Source table: `{snapshot.table}` ({table_label}), {row_count} row(s).\n"
        f"The first sentence MUST follow this pattern:\n"
        f"「{table_label}包含{row_count}条记录，」then describe the records.\n"
        f"Do NOT describe schema (primary keys, foreign keys, column names, or referenced tables).\n"
        f"{registry_block}\n"
        f"---Table Data---\n{payload}"
    )

    response = await llm_func(user_prompt, system_prompt=system_prompt)
    if not isinstance(response, str):
        response = str(response)
    cleaned = remove_think_tags(response).strip()
    if not cleaned:
        raise RuntimeError(f"LLM returned empty text for table '{snapshot.table}'")
    return cleaned


async def convert_csv_rows_to_natural_language(
    rag: LightRAG,
    *,
    snapshot: CsvSnapshot,
    language: str,
    system_prompt_template: str | None = None,
    max_prompt_chars: int = 120_000,
) -> str:
    llm_func = rag.role_llm_funcs.get("query") or rag.llm_model_func
    if llm_func is None:
        raise RuntimeError("No LLM function configured for natural-language conversion")

    system_prompt = (system_prompt_template or DEFAULT_CSV_TO_TEXT_SYSTEM_PROMPT).format(
        language=language
    )
    payload = build_csv_prompt_payload(snapshot)
    if len(payload) > max_prompt_chars:
        payload = payload[:max_prompt_chars] + "\n... [truncated for LLM input limit]"

    dataset_label = snapshot.name
    row_count = len(snapshot.rows)
    user_prompt = (
        f"Convert the following CSV export into natural language.\n"
        f"Source dataset: `{snapshot.name}`, {row_count} row(s).\n"
        f"The first sentence MUST follow this pattern:\n"
        f"「{dataset_label}包含{row_count}条记录，」then describe the records.\n"
        f"Do NOT describe schema (column names, delimiters, or file structure).\n"
        f"---CSV Data---\n{payload}"
    )

    response = await llm_func(user_prompt, system_prompt=system_prompt)
    if not isinstance(response, str):
        response = str(response)
    cleaned = remove_think_tags(response).strip()
    if not cleaned:
        raise RuntimeError(f"LLM returned empty text for CSV '{snapshot.name}'")
    return cleaned


async def import_csv_file(
    rag: LightRAG,
    *,
    csv_path: str,
    max_rows: int,
    language: str,
    file_source_prefix: str | None,
    chunking: Any | None,
    pipeline_index_texts,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    get_doc_status_value,
    generate_track_id,
    working_dir: str | None = None,
    csv_delimiter: str | None = None,
    dataset_name: str | None = None,
) -> list[SqliteTableConversionResult]:
    """Convert a CSV file to NL and enqueue via ``pipeline_index_texts``."""
    path = resolve_csv_file_path(csv_path, working_dir=working_dir)
    snapshot = read_csv_snapshot(
        path,
        max_rows=max_rows,
        delimiter=csv_delimiter,
        dataset_name=dataset_name,
    )

    file_source = default_file_source_for_csv(path, file_source_prefix)
    normalized_source = normalize_file_path(file_source)
    track_id = generate_track_id("csv")
    table_label = snapshot.name

    if not snapshot.rows:
        return [
            SqliteTableConversionResult(
                table=table_label,
                file_source=normalized_source,
                track_id=track_id,
                row_count=0,
                text_chars=0,
                status="skipped",
                error="CSV has no data rows",
            )
        ]

    try:
        existing_doc = await get_existing_doc_by_file_path_candidates(
            rag.doc_status, normalized_source
        )
        if existing_doc:
            status = get_doc_status_value(existing_doc) or "unknown"
            return [
                SqliteTableConversionResult(
                    table=table_label,
                    file_source=normalized_source,
                    track_id=track_id,
                    row_count=0,
                    text_chars=0,
                    status="skipped",
                    error=(
                        f"Document already exists for '{normalized_source}' "
                        f"(status={status}). Delete it before re-importing."
                    ),
                )
            ]

        nl_text = await convert_csv_rows_to_natural_language(
            rag,
            snapshot=snapshot,
            language=language,
        )
        await pipeline_index_texts(
            rag,
            [nl_text],
            file_sources=[normalized_source],
            track_id=track_id,
            chunking=chunking,
        )
        logger.info(
            "[csv_import] Queued dataset '%s' (%s rows, %s chars) track_id=%s",
            table_label,
            len(snapshot.rows),
            len(nl_text),
            track_id,
        )
        return [
            SqliteTableConversionResult(
                table=table_label,
                file_source=normalized_source,
                track_id=track_id,
                row_count=len(snapshot.rows),
                text_chars=len(nl_text),
                status="queued",
            )
        ]
    except Exception as exc:
        logger.error("[csv_import] Failed dataset '%s': %s", table_label, exc, exc_info=True)
        return [
            SqliteTableConversionResult(
                table=table_label,
                file_source=normalized_source,
                track_id=track_id,
                row_count=0,
                text_chars=0,
                status="failed",
                error=str(exc),
            )
        ]


async def convert_registry_to_natural_language(
    rag: LightRAG,
    *,
    registry_text: str,
    language: str,
    max_prompt_chars: int = 120_000,
) -> str:
    llm_func = rag.role_llm_funcs.get("query") or rag.llm_model_func
    if llm_func is None:
        raise RuntimeError("No LLM function configured for natural-language conversion")

    system_prompt = CROSS_TABLE_REGISTRY_SYSTEM_PROMPT.format(language=language)
    payload = registry_text
    if len(payload) > max_prompt_chars:
        payload = payload[:max_prompt_chars] + "\n... [truncated for LLM input limit]"

    user_prompt = (
        "Convert the following cross-table entity registry into natural language "
        "that emphasizes shared identities across tables.\n\n"
        f"---Entity Registry---\n{payload}"
    )
    response = await llm_func(user_prompt, system_prompt=system_prompt)
    if not isinstance(response, str):
        response = str(response)
    cleaned = remove_think_tags(response).strip()
    if not cleaned:
        raise RuntimeError("LLM returned empty text for cross-table entity registry")
    return cleaned


def default_registry_file_source(db_path: Path, prefix: str | None = None) -> str:
    base = f"sqlite_{db_path.stem}_entity_registry.txt"
    if prefix:
        cleaned = prefix.strip().rstrip("/")
        return f"{cleaned}/{base}"
    return base


async def import_sqlite_tables(
    rag: LightRAG,
    *,
    database_path: str,
    tables: Iterable[str] | None,
    max_rows_per_table: int,
    language: str,
    file_source_prefix: str | None,
    chunking: Any | None,
    pipeline_index_texts,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    get_doc_status_value,
    generate_track_id,
    working_dir: str | None = None,
    resolve_cross_table_links: bool = True,
) -> list[SqliteTableConversionResult]:
    """Convert each requested table to NL and enqueue via ``pipeline_index_texts``."""
    db_path = resolve_sqlite_database_path(database_path, working_dir=working_dir)
    available_tables = list_sqlite_tables(db_path)
    if not available_tables:
        raise ValueError(f"No user tables found in database: {db_path}")

    if tables:
        requested = [_validate_table_name(t) for t in tables]
        missing = sorted(set(requested) - set(available_tables))
        if missing:
            raise ValueError(
                f"Unknown table(s): {', '.join(missing)}. "
                f"Available: {', '.join(available_tables)}"
            )
        target_tables = requested
    else:
        target_tables = available_tables

    snapshots: dict[str, SqliteTableSnapshot] = {}
    for table in target_tables:
        snapshot = fetch_sqlite_table_snapshot(
            db_path, table, max_rows=max_rows_per_table
        )
        snapshots[table] = snapshot

    registry: dict[str, dict[Any, dict[str, Any]]] = {}
    meta: dict[str, TableMeta] = {}
    pk_by_table: dict[str, str] = {}
    registry_guidance_text: str | None = None

    if resolve_cross_table_links:
        registry, meta = build_entity_registry(db_path, snapshots)
        pk_by_table = {table: table_meta.primary_key for table, table_meta in meta.items()}
        registry_guidance_text = build_registry_document_text(
            registry,
            meta,
            snapshots=snapshots,
            pk_by_table=pk_by_table,
        )
        target_tables = sort_tables_by_foreign_key_dependencies(
            target_tables,
            snapshots,
            pk_by_table,
        )

    results: list[SqliteTableConversionResult] = []

    for table in target_tables:
        file_source = default_file_source_for_table(db_path, table, file_source_prefix)
        normalized_source = normalize_file_path(file_source)
        track_id = generate_track_id("sqlite")

        try:
            snapshot = snapshots[table]
            if not snapshot.rows:
                results.append(
                    SqliteTableConversionResult(
                        table=table,
                        file_source=normalized_source,
                        track_id=track_id,
                        row_count=0,
                        text_chars=0,
                        status="skipped",
                        error="Table is empty",
                    )
                )
                continue

            existing_doc = await get_existing_doc_by_file_path_candidates(
                rag.doc_status, normalized_source
            )
            if existing_doc:
                status = get_doc_status_value(existing_doc) or "unknown"
                results.append(
                    SqliteTableConversionResult(
                        table=table,
                        file_source=normalized_source,
                        track_id=track_id,
                        row_count=0,
                        text_chars=0,
                        status="skipped",
                        error=(
                            f"Document already exists for '{normalized_source}' "
                            f"(status={status}). Delete it before re-importing."
                        ),
                    )
                )
                continue

            nl_text = await convert_table_rows_to_natural_language(
                rag,
                snapshot=snapshot,
                language=language,
                registry=registry if resolve_cross_table_links else None,
                meta=meta if resolve_cross_table_links else None,
                pk_by_table=pk_by_table if resolve_cross_table_links else None,
                cross_table_registry_text=registry_guidance_text
                if resolve_cross_table_links
                else None,
            )

            await pipeline_index_texts(
                rag,
                [nl_text],
                file_sources=[normalized_source],
                track_id=track_id,
                chunking=chunking,
            )

            results.append(
                SqliteTableConversionResult(
                    table=table,
                    file_source=normalized_source,
                    track_id=track_id,
                    row_count=len(snapshot.rows),
                    text_chars=len(nl_text),
                    status="queued",
                )
            )
            logger.info(
                "[sqlite_import] Queued table '%s' (%s rows, %s chars) track_id=%s",
                table,
                len(snapshot.rows),
                len(nl_text),
                track_id,
            )
        except Exception as exc:
            logger.error(
                "[sqlite_import] Failed table '%s': %s", table, exc, exc_info=True
            )
            results.append(
                SqliteTableConversionResult(
                    table=table,
                    file_source=normalized_source,
                    track_id=track_id,
                    row_count=0,
                    text_chars=0,
                    status="failed",
                    error=str(exc),
                )
            )

    return results


_CATALOG_ID_COLUMNS = ("id", "object_code", "table_id", "resource_id", "resource_code")
_CATALOG_NAME_COLUMNS = ("physical_name", "table_name", "object_name")
_CATALOG_TABLES = ("dts_meta_object", "meta_object", "resource_meta_object")


def _lookup_table_in_catalog(db_path: Path, table_id: str) -> str | None:
    """Resolve a catalog id/code to a physical SQLite table name when present."""
    with _connect_readonly(db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for catalog in _CATALOG_TABLES:
            if catalog not in existing_tables:
                continue
            columns = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({catalog!r})").fetchall()
            }
            name_columns = [c for c in _CATALOG_NAME_COLUMNS if c in columns]
            if not name_columns:
                continue
            for id_col in _CATALOG_ID_COLUMNS:
                if id_col not in columns:
                    continue
                for name_col in name_columns:
                    row = conn.execute(
                        f"SELECT {name_col} FROM {catalog!r} WHERE {id_col} = ? LIMIT 1",
                        (table_id,),
                    ).fetchone()
                    if row and row[0]:
                        return str(row[0]).strip()
    return None


def resolve_sqlite_table_reference(
    db_path: Path,
    *,
    table_name: str | None = None,
    table_id: str | None = None,
) -> str:
    """Resolve ``table_name`` or catalog ``table_id`` to a SQLite table name."""
    if table_name and table_id:
        raise ValueError("Provide either table_name or table_id, not both")
    if not table_name and not table_id:
        raise ValueError("Either table_name or table_id is required")

    available = set(list_sqlite_tables(db_path))

    if table_name:
        name = _validate_table_name(table_name)
        if name not in available:
            raise ValueError(
                f"Unknown table '{name}'. Available: {', '.join(sorted(available))}"
            )
        return name

    ref = str(table_id or "").strip()
    if not ref:
        raise ValueError("table_id must not be empty")

    if _TABLE_NAME_RE.match(ref) and ref in available:
        return ref

    resolved = _lookup_table_in_catalog(db_path, ref)
    if resolved:
        resolved_name = _validate_table_name(resolved)
        if resolved_name not in available:
            raise ValueError(
                f"Catalog id '{ref}' maps to '{resolved_name}', "
                "which is not present in this database"
            )
        return resolved_name

    raise ValueError(
        f"Cannot resolve table_id '{ref}' to a SQLite table. "
        f"Available tables: {', '.join(sorted(available))}"
    )


def file_source_candidates_for_table(
    db_path: Path,
    table: str,
    file_source_prefix: str | None,
) -> list[str]:
    """Return likely document file_source values for a SQLite table import."""
    candidates: list[str] = []
    for prefix in (file_source_prefix, None, "sqlite_import"):
        if prefix == "":
            continue
        source = default_file_source_for_table(db_path, table, prefix)
        if source not in candidates:
            candidates.append(source)
    return candidates


async def find_sqlite_table_document(
    rag: LightRAG,
    *,
    database_path: str,
    table_name: str | None = None,
    table_id: str | None = None,
    file_source_prefix: str | None = None,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    working_dir: str | None = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return (resolved_table, file_source, existing_doc_or_none)."""
    db_path = resolve_sqlite_database_path(database_path, working_dir=working_dir)
    resolved_table = resolve_sqlite_table_reference(
        db_path, table_name=table_name, table_id=table_id
    )
    for candidate in file_source_candidates_for_table(
        db_path, resolved_table, file_source_prefix
    ):
        normalized = normalize_file_path(candidate)
        existing = await get_existing_doc_by_file_path_candidates(
            rag.doc_status, normalized
        )
        if existing:
            return resolved_table, normalized, existing
    fallback = normalize_file_path(
        default_file_source_for_table(db_path, resolved_table, file_source_prefix)
    )
    return resolved_table, fallback, None


@dataclass
class SqliteTableDeleteResult:
    table: str
    file_source: str
    doc_id: str | None
    status: str
    message: str
    error: str | None = None


async def delete_sqlite_table_document(
    rag: LightRAG,
    *,
    database_path: str,
    table_name: str | None = None,
    table_id: str | None = None,
    file_source_prefix: str | None = None,
    normalize_file_path,
    get_existing_doc_by_file_path_candidates,
    working_dir: str | None = None,
    delete_llm_cache: bool = False,
) -> SqliteTableDeleteResult:
    """Delete the LightRAG document (and graph) for one SQLite table import."""
    resolved_table, file_source, existing = await find_sqlite_table_document(
        rag,
        database_path=database_path,
        table_name=table_name,
        table_id=table_id,
        file_source_prefix=file_source_prefix,
        normalize_file_path=normalize_file_path,
        get_existing_doc_by_file_path_candidates=get_existing_doc_by_file_path_candidates,
        working_dir=working_dir,
    )
    if not existing:
        return SqliteTableDeleteResult(
            table=resolved_table,
            file_source=file_source,
            doc_id=None,
            status="not_found",
            message=(
                f"No imported document found for table '{resolved_table}' "
                f"(expected file_source like '{file_source}')"
            ),
        )

    doc_id = str(existing.get("id") or existing.get("doc_id") or "").strip()
    if not doc_id:
        return SqliteTableDeleteResult(
            table=resolved_table,
            file_source=file_source,
            doc_id=None,
            status="failed",
            message="Matched document record is missing an id",
            error="missing_doc_id",
        )

    result = await rag.adelete_by_doc_id(doc_id, delete_llm_cache=delete_llm_cache)
    if getattr(result, "status", None) == "success":
        return SqliteTableDeleteResult(
            table=resolved_table,
            file_source=file_source,
            doc_id=doc_id,
            status="success",
            message=f"Deleted document and graph data for table '{resolved_table}'",
        )

    error = getattr(result, "message", None) or getattr(result, "status", "delete_failed")
    return SqliteTableDeleteResult(
        table=resolved_table,
        file_source=file_source,
        doc_id=doc_id,
        status="failed",
        message=f"Failed to delete document for table '{resolved_table}'",
        error=str(error),
    )