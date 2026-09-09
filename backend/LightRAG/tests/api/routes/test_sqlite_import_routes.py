"""Offline tests for SQLite import helpers and routes."""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
_service = importlib.import_module("lightrag.api.sqlite_import_service")
_routes = importlib.import_module("lightrag.api.routers.sqlite_import_routes")
sys.argv = _original_argv

create_sqlite_import_routes = _routes.create_sqlite_import_routes
resolve_sqlite_database_path = _service.resolve_sqlite_database_path
list_sqlite_tables = _service.list_sqlite_tables
fetch_sqlite_table_snapshot = _service.fetch_sqlite_table_snapshot
import_sqlite_tables = _service.import_sqlite_tables
build_entity_registry = _service.build_entity_registry
enrich_row_with_foreign_keys = _service.enrich_row_with_foreign_keys
infer_foreign_key_target = _service.infer_foreign_key_target
build_cross_table_registry_text = _service.build_cross_table_registry_text
build_registry_document_text = _service.build_registry_document_text
parse_sqlite_table_from_file_path = importlib.import_module(
    "lightrag.sqlite_import_context"
).parse_sqlite_table_from_file_path
resolve_sqlite_table_reference = _service.resolve_sqlite_table_reference
file_source_candidates_for_table = _service.file_source_candidates_for_table
delete_sqlite_table_document = _service.delete_sqlite_table_document
find_sqlite_table_document = _service.find_sqlite_table_document
parse_sqlite_import_tables_form = _service.parse_sqlite_import_tables_form
save_uploaded_sqlite_database = _service.save_uploaded_sqlite_database
sqlite_upload_dir = _service.sqlite_upload_dir

pytestmark = pytest.mark.offline


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT, team TEXT)")
        conn.execute(
            "INSERT INTO players (name, team) VALUES ('艾顿', '湖人'), ('申京', '火箭')"
        )
        conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, city TEXT)")
        conn.execute("INSERT INTO teams (city) VALUES ('洛杉矶')")
        conn.commit()
    finally:
        conn.close()


def _make_linked_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE pilot (
                pilot_id INTEGER PRIMARY KEY,
                pilot_name TEXT NOT NULL
            );
            CREATE TABLE flight_training (
                training_id INTEGER PRIMARY KEY,
                training_name TEXT NOT NULL,
                pilot_id INTEGER NOT NULL,
                score INTEGER NOT NULL
            );
            INSERT INTO pilot VALUES (1, '张磊'), (2, '刘佳');
            INSERT INTO flight_training VALUES
                (1, '基础科目恢复训练', 1, 92),
                (2, '复杂气象课目', 2, 88);
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sample.sqlite"
    _make_db(db_path)
    monkeypatch.setenv("SQLITE_IMPORT_ALLOWED_DIRS", str(tmp_path))
    return db_path


def test_resolve_sqlite_database_path_requires_allowed_root(sqlite_db):
    resolved = resolve_sqlite_database_path(str(sqlite_db))
    assert resolved == sqlite_db.resolve()


def test_resolve_sqlite_database_path_rejects_outside_allowed(tmp_path, monkeypatch):
    db_path = tmp_path / "outside.sqlite"
    _make_db(db_path)
    monkeypatch.setenv("SQLITE_IMPORT_ALLOWED_DIRS", str(tmp_path / "allowed"))
    with pytest.raises(ValueError, match="outside SQLITE_IMPORT_ALLOWED_DIRS"):
        resolve_sqlite_database_path(str(db_path))


def test_list_and_fetch_sqlite_tables(sqlite_db):
    tables = list_sqlite_tables(sqlite_db)
    assert tables == ["players", "teams"]

    snapshot = fetch_sqlite_table_snapshot(sqlite_db, "players", max_rows=10)
    assert snapshot.table == "players"
    assert len(snapshot.rows) == 2
    assert snapshot.columns == ["id", "name", "team"]


@pytest.fixture()
def linked_sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "linked.sqlite"
    _make_linked_db(db_path)
    monkeypatch.setenv("SQLITE_IMPORT_ALLOWED_DIRS", str(tmp_path))
    return db_path


def test_infer_foreign_key_target_for_pilot_id():
    pk_by_table = {"pilot": "pilot_id", "flight_training": "training_id"}
    assert infer_foreign_key_target("pilot_id", pk_by_table) == ("pilot", "pilot_id")
    assert infer_foreign_key_target("lead_pilot_id", pk_by_table) == ("pilot", "pilot_id")


def test_infer_foreign_key_target_pilot_id_not_generic_id(tmp_path, monkeypatch):
    """pilot_id must not resolve to the first table whose PK happens to be ``id``."""
    db_path = tmp_path / "denormalized.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE assessment_record (
                id INTEGER PRIMARY KEY,
                pilot_id INTEGER,
                pilot_name TEXT
            );
            CREATE TABLE pilot_ability_profile (
                id INTEGER PRIMARY KEY,
                pilot_id INTEGER,
                pilot_name TEXT
            );
            INSERT INTO assessment_record VALUES (3, 2, '李强');
            INSERT INTO pilot_ability_profile VALUES (3, 3, '王磊');
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("SQLITE_IMPORT_ALLOWED_DIRS", str(tmp_path))
    snapshots = {
        "assessment_record": fetch_sqlite_table_snapshot(
            db_path, "assessment_record", max_rows=10
        ),
        "pilot_ability_profile": fetch_sqlite_table_snapshot(
            db_path, "pilot_ability_profile", max_rows=10
        ),
    }
    registry, meta = build_entity_registry(db_path, snapshots)
    pk_by_table = {table: table_meta.primary_key for table, table_meta in meta.items()}

    assert infer_foreign_key_target("pilot_id", pk_by_table) is None

    wang_lei = registry["pilot_ability_profile"][3]
    enriched = enrich_row_with_foreign_keys(
        wang_lei,
        registry=registry,
        meta=meta,
        pk_by_table=pk_by_table,
    )
    assert "__pilot_id_canonical_name" not in enriched
    assert enriched["pilot_name"] == "王磊"


def test_enrich_row_resolves_pilot_name(linked_sqlite_db):
    snapshots = {
        "pilot": fetch_sqlite_table_snapshot(linked_sqlite_db, "pilot", max_rows=10),
        "flight_training": fetch_sqlite_table_snapshot(
            linked_sqlite_db, "flight_training", max_rows=10
        ),
    }
    registry, meta = build_entity_registry(linked_sqlite_db, snapshots)
    pk_by_table = {table: table_meta.primary_key for table, table_meta in meta.items()}
    enriched = enrich_row_with_foreign_keys(
        snapshots["flight_training"].rows[0],
        registry=registry,
        meta=meta,
        pk_by_table=pk_by_table,
    )
    assert enriched["__pilot_id_canonical_name"] == "张磊"
    assert "张磊" in enriched["__pilot_id_entity_ref"]
    assert any("张磊" in link for link in enriched["__foreign_key_links"])


def test_build_cross_table_registry_text_contains_pilot(linked_sqlite_db):
    snapshots = {
        "pilot": fetch_sqlite_table_snapshot(linked_sqlite_db, "pilot", max_rows=10),
        "flight_training": fetch_sqlite_table_snapshot(
            linked_sqlite_db, "flight_training", max_rows=10
        ),
    }
    registry, meta = build_entity_registry(linked_sqlite_db, snapshots)
    text = build_cross_table_registry_text(registry, meta)
    assert "pilot.pilot_id=1 → 张磊" in text


def test_parse_sqlite_table_from_file_path():
    assert parse_sqlite_table_from_file_path("sqlite_military-task_pilot.txt") == (
        "pilot",
        "飞行员表",
    )
    assert parse_sqlite_table_from_file_path(
        "sqlite_import/sqlite_military-task_flight_training.txt"
    ) == ("flight_training", "飞行训练表")
    assert parse_sqlite_table_from_file_path("sqlite_military-task_entity_registry.txt") is None
    assert parse_sqlite_table_from_file_path("other.txt") is None


def test_build_registry_document_text_lists_all_pilots(linked_sqlite_db):
    snapshots = {
        "pilot": fetch_sqlite_table_snapshot(linked_sqlite_db, "pilot", max_rows=10),
        "flight_training": fetch_sqlite_table_snapshot(
            linked_sqlite_db, "flight_training", max_rows=10
        ),
    }
    registry, meta = build_entity_registry(linked_sqlite_db, snapshots)
    pk_by_table = {table: table_meta.primary_key for table, table_meta in meta.items()}
    text = build_registry_document_text(
        registry,
        meta,
        snapshots=snapshots,
        pk_by_table=pk_by_table,
    )
    assert "pilot.pilot_id=1 → 张磊" in text
    assert "pilot.pilot_id=2 → 刘佳" in text
    assert "飞行员表通过pilot_id=1包含实体「张磊」" in text
    assert "飞行员表通过pilot_id=2包含实体「刘佳」" in text
    assert "id=1 举例" not in text


@pytest.mark.asyncio
async def test_import_sqlite_tables_with_cross_table_links(linked_sqlite_db):
    rag = SimpleNamespace(
        working_dir=str(linked_sqlite_db.parent),
        role_llm_funcs={
            "query": AsyncMock(
                side_effect=[
                    "pilot 飞行员表：张磊是飞行员。",
                    "flight_training 飞行训练表：pilot_id=1 的训练记录属于飞行员张磊。",
                    "flight_training 飞行训练表：pilot_id=2 的训练记录属于飞行员刘佳。",
                ]
            )
        },
        llm_model_func=None,
        doc_status=SimpleNamespace(),
    )

    pipeline_index_texts = AsyncMock()
    get_existing = AsyncMock(return_value=None)

    results = await import_sqlite_tables(
        rag,
        database_path=str(linked_sqlite_db),
        tables=["flight_training", "pilot"],
        max_rows_per_table=50,
        language="Chinese",
        file_source_prefix="sqlite_import",
        chunking=None,
        pipeline_index_texts=pipeline_index_texts,
        normalize_file_path=lambda value: value,
        get_existing_doc_by_file_path_candidates=get_existing,
        get_doc_status_value=lambda doc: getattr(doc, "status", "unknown"),
        generate_track_id=lambda prefix: f"{prefix}_test",
        working_dir=str(linked_sqlite_db.parent),
        resolve_cross_table_links=True,
    )

    assert pipeline_index_texts.await_count == 2
    queued_tables = {item.table for item in results if item.status == "queued"}
    assert "pilot" in queued_tables
    assert "flight_training" in queued_tables
    assert "__entity_registry__" not in queued_tables
    first_call_text = pipeline_index_texts.await_args_list[0].args[1][0]
    assert "pilot" in first_call_text or "飞行员表" in first_call_text


@pytest.mark.asyncio
async def test_import_sqlite_tables_queues_documents(sqlite_db):
    rag = SimpleNamespace(
        working_dir=str(sqlite_db.parent),
        role_llm_funcs={
            "query": AsyncMock(
                return_value="艾顿效力于湖人队。申京效力于火箭队。"
            )
        },
        llm_model_func=None,
        doc_status=SimpleNamespace(),
    )

    pipeline_index_texts = AsyncMock()
    get_existing = AsyncMock(return_value=None)

    results = await import_sqlite_tables(
        rag,
        database_path=str(sqlite_db),
        tables=["players"],
        max_rows_per_table=50,
        language="Chinese",
        file_source_prefix="sqlite_import",
        chunking=None,
        pipeline_index_texts=pipeline_index_texts,
        normalize_file_path=lambda value: value,
        get_existing_doc_by_file_path_candidates=get_existing,
        get_doc_status_value=lambda doc: getattr(doc, "status", "unknown"),
        generate_track_id=lambda prefix: f"{prefix}_test",
        working_dir=str(sqlite_db.parent),
    )

    assert len(results) == 1
    assert results[0].status == "queued"
    assert results[0].row_count == 2
    pipeline_index_texts.assert_awaited_once()
    args, kwargs = pipeline_index_texts.await_args
    assert "艾顿" in args[1][0]
    assert kwargs["file_sources"] == ["sqlite_import/sqlite_sample_players.txt"]


def test_sqlite_tables_route(sqlite_db):
    rag = SimpleNamespace(working_dir=str(sqlite_db.parent))

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    response = client.get(
        "/sqlite/tables",
        params={"database_path": str(sqlite_db)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tables"] == ["players", "teams"]


def test_resolve_sqlite_table_reference_by_name(linked_sqlite_db):
    resolved = resolve_sqlite_table_reference(
        linked_sqlite_db, table_name="pilot"
    )
    assert resolved == "pilot"


def test_resolve_sqlite_table_reference_by_id_as_name(linked_sqlite_db):
    resolved = resolve_sqlite_table_reference(
        linked_sqlite_db, table_id="flight_training"
    )
    assert resolved == "flight_training"


def test_resolve_sqlite_table_reference_rejects_unknown(sqlite_db):
    with pytest.raises(ValueError, match="Unknown table"):
        resolve_sqlite_table_reference(sqlite_db, table_name="missing")


def test_file_source_candidates_for_table(linked_sqlite_db):
    candidates = file_source_candidates_for_table(
        linked_sqlite_db, "pilot", "sqlite_import"
    )
    assert "sqlite_import/sqlite_linked_pilot.txt" in candidates
    assert "sqlite_linked_pilot.txt" in candidates


@pytest.mark.asyncio
async def test_delete_sqlite_table_document_not_found(linked_sqlite_db):
    rag = SimpleNamespace(
        working_dir=str(linked_sqlite_db.parent),
        doc_status=SimpleNamespace(),
    )

    async def _no_doc(*_args, **_kwargs):
        return None

    result = await delete_sqlite_table_document(
        rag,
        database_path=str(linked_sqlite_db),
        table_name="pilot",
        normalize_file_path=lambda value: value,
        get_existing_doc_by_file_path_candidates=_no_doc,
        working_dir=str(linked_sqlite_db.parent),
    )
    assert result.status == "not_found"


def test_sqlite_table_upload_route(linked_sqlite_db, monkeypatch):
    rag = SimpleNamespace(
        working_dir=str(linked_sqlite_db.parent),
        workspace="task_id_2",
        role_llm_funcs={
            "query": AsyncMock(return_value="飞行员张磊。"),
        },
        llm_model_func=None,
        doc_status=SimpleNamespace(),
    )

    async def _noop_reserve(_rag):
        return False

    async def _noop_release(_rag):
        return None

    monkeypatch.setattr(_routes, "_reserve_enqueue_slot", _noop_reserve)
    monkeypatch.setattr(_routes, "_release_enqueue_slot", _noop_release)
    monkeypatch.setattr(
        _service,
        "import_sqlite_tables",
        AsyncMock(
            return_value=[
                _service.SqliteTableConversionResult(
                    table="pilot",
                    file_source="sqlite_military-task_pilot.txt",
                    track_id="sqlite_test",
                    row_count=2,
                    text_chars=12,
                    status="queued",
                )
            ]
        ),
    )

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    response = client.post(
        "/sqlite/table/upload",
        headers={"LIGHTRAG-WORKSPACE": "task_id_2"},
        json={
            "task_space_id": "task_id_2",
            "database_path": str(linked_sqlite_db),
            "table_name": "pilot",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["table"] == "pilot"


def test_sqlite_table_delete_route(linked_sqlite_db, monkeypatch):
    rag = SimpleNamespace(
        working_dir=str(linked_sqlite_db.parent),
        workspace="task_id_2",
        doc_status=SimpleNamespace(),
    )

    async def _acquire(_rag):
        return True, None

    async def _release(_rag):
        return None

    monkeypatch.setattr(_routes, "_acquire_destructive_busy", _acquire)
    monkeypatch.setattr(_routes, "_release_destructive_busy", _release)
    monkeypatch.setattr(
        _routes,
        "delete_sqlite_table_document",
        AsyncMock(
            return_value=_service.SqliteTableDeleteResult(
                table="pilot",
                file_source="sqlite_military-task_pilot.txt",
                doc_id="doc-1",
                status="success",
                message="deleted",
            )
        ),
    )

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    response = client.post(
        "/sqlite/table/delete",
        headers={"LIGHTRAG-WORKSPACE": "task_id_2"},
        json={
            "task_space_id": "task_id_2",
            "database_path": str(linked_sqlite_db),
            "table_name": "pilot",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["doc_id"] == "doc-1"


def test_parse_sqlite_import_tables_form():
    assert parse_sqlite_import_tables_form(None) is None
    assert parse_sqlite_import_tables_form("pilot,team") == ["pilot", "team"]
    assert parse_sqlite_import_tables_form('["pilot", "team"]') == ["pilot", "team"]


def test_resolve_sqlite_database_path_allows_upload_dir(tmp_path):
    working_dir = tmp_path / "rag"
    upload_dir = working_dir / "sqlite_uploads"
    upload_dir.mkdir(parents=True)
    db_path = upload_dir / "abc123_sample.db"
    _make_db(db_path)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("SQLITE_IMPORT_ALLOWED_DIRS", str(tmp_path / "other"))
    try:
        resolved = resolve_sqlite_database_path(
            str(db_path), working_dir=str(working_dir)
        )
        assert resolved == db_path.resolve()
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_save_uploaded_sqlite_database(tmp_path):
    db_path = tmp_path / "source.sqlite"
    _make_db(db_path)
    working_dir = tmp_path / "rag"

    class _FakeUpload:
        def __init__(self, data: bytes):
            self._data = data
            self.filename = "remote.sqlite"

        async def read(self, size: int = -1):
            if not self._data:
                return b""
            if size < 0:
                chunk, self._data = self._data, b""
                return chunk
            chunk = self._data[:size]
            self._data = self._data[size:]
            return chunk

    saved = await save_uploaded_sqlite_database(
        _FakeUpload(db_path.read_bytes()),
        working_dir=str(working_dir),
        original_filename="remote.sqlite",
    )
    assert saved.parent == sqlite_upload_dir(str(working_dir))
    assert list_sqlite_tables(saved) == ["players", "teams"]


def test_import_sync_multipart_route(sqlite_db, monkeypatch):
    rag = SimpleNamespace(working_dir=str(sqlite_db.parent))

    async def _noop_reserve(_rag):
        return False

    async def _noop_release(_rag):
        return None

    monkeypatch.setattr(_routes, "_reserve_enqueue_slot", _noop_reserve)
    monkeypatch.setattr(_routes, "_release_enqueue_slot", _noop_release)
    monkeypatch.setattr(
        _routes,
        "probe_import_models",
        AsyncMock(return_value=(True, None)),
    )
    import_mock = AsyncMock(
        return_value=[
            _service.SqliteTableConversionResult(
                table="players",
                file_source="sqlite_import/sqlite_sample_players.txt",
                track_id="sqlite_test",
                row_count=2,
                text_chars=42,
                status="queued",
            )
        ]
    )
    monkeypatch.setattr(_service, "import_sqlite_tables", import_mock)

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    with sqlite_db.open("rb") as handle:
        response = client.post(
            "/sqlite/import_sync",
            files={"file": ("sample.sqlite", handle, "application/octet-stream")},
            data={
                "tables": "players",
                "language": "Chinese",
                "file_source_prefix": "sqlite_import",
                "resolve_cross_table_links": "true",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["source_type"] == "sqlite"
    assert payload["results"][0]["table"] == "players"
    assert "sqlite_uploads" in payload["database_path"]
    import_mock.assert_awaited_once()


def test_import_sync_json_deferred_when_models_unavailable(sqlite_db, monkeypatch):
    rag = SimpleNamespace(working_dir=str(sqlite_db.parent))

    reserve_mock = AsyncMock(return_value=False)
    release_mock = AsyncMock(return_value=None)
    json_import_mock = AsyncMock(
        return_value=[
            _service.SqliteTableConversionResult(
                table="players",
                file_source="sqlite_import/sqlite_sample_players.json",
                track_id="sqlite_json_test",
                row_count=2,
                text_chars=42,
                status="json_queued",
            )
        ]
    )
    import_mock = AsyncMock()

    monkeypatch.setattr(_routes, "_reserve_enqueue_slot", reserve_mock)
    monkeypatch.setattr(_routes, "_release_enqueue_slot", release_mock)
    monkeypatch.setattr(
        _routes,
        "probe_import_models",
        AsyncMock(return_value=(False, "LLM probe timed out")),
    )
    monkeypatch.setattr(_routes, "import_sqlite_tables_as_json", json_import_mock)
    monkeypatch.setattr(_service, "import_sqlite_tables", import_mock)

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    with sqlite_db.open("rb") as handle:
        response = client.post(
            "/sqlite/import_sync",
            files={"file": ("sample.sqlite", handle, "application/octet-stream")},
            data={"tables": "players"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "json_deferred"
    assert payload["results"][0]["status"] == "json_queued"
    assert payload["results"][0]["file_source"].endswith(".json")
    assert "incomplete" in payload["message"]
    json_import_mock.assert_awaited_once()
    import_mock.assert_not_called()
    reserve_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_import_models_success(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_LLM_ENABLED", "true")
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_ENABLED", "true")
    llm_mock = AsyncMock(return_value="ok")
    embed_mock = AsyncMock(return_value=[[0.1, 0.2]])
    rag = SimpleNamespace(
        role_llm_funcs={"query": llm_mock},
        llm_model_func=None,
        embedding_func=embed_mock,
    )

    ok, reason = await _service.probe_import_models(rag, timeout_sec=5.0)

    assert ok is True
    assert reason is None
    llm_mock.assert_awaited_once()
    embed_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_import_models_llm_disabled(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_LLM_ENABLED", "false")
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_ENABLED", "true")
    llm_mock = AsyncMock(return_value="ok")
    embed_mock = AsyncMock(return_value=[[0.1]])
    rag = SimpleNamespace(
        role_llm_funcs={"query": llm_mock},
        llm_model_func=None,
        embedding_func=embed_mock,
    )

    ok, reason = await _service.probe_import_models(rag, timeout_sec=5.0)

    assert ok is False
    assert reason is not None
    assert "LLM disabled" in reason
    llm_mock.assert_not_called()
    embed_mock.assert_not_called()


@pytest.mark.asyncio
async def test_probe_import_models_embedding_disabled(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_LLM_ENABLED", "true")
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_ENABLED", "false")
    llm_mock = AsyncMock(return_value="ok")
    embed_mock = AsyncMock(return_value=[[0.1]])
    rag = SimpleNamespace(
        role_llm_funcs={"query": llm_mock},
        llm_model_func=None,
        embedding_func=embed_mock,
    )

    ok, reason = await _service.probe_import_models(rag, timeout_sec=5.0)

    assert ok is False
    assert reason is not None
    assert "Embedding disabled" in reason
    llm_mock.assert_not_called()
    embed_mock.assert_not_called()


@pytest.mark.asyncio
async def test_probe_import_models_fails_on_embedding(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_LLM_ENABLED", "true")
    monkeypatch.setenv("LIGHTRAG_EMBEDDING_ENABLED", "true")
    llm_mock = AsyncMock(return_value="ok")
    embed_mock = AsyncMock(side_effect=RuntimeError("connection refused"))
    rag = SimpleNamespace(
        role_llm_funcs={"query": llm_mock},
        llm_model_func=None,
        embedding_func=embed_mock,
    )

    ok, reason = await _service.probe_import_models(rag, timeout_sec=5.0)

    assert ok is False
    assert reason is not None
    assert "Embedding unavailable" in reason


def test_read_csv_snapshot(tmp_path):
    csv_path = tmp_path / "pilots.csv"
    csv_path.write_text(
        "pilot_id,pilot_name,score\n1,张磊,92\n2,刘佳,88\n",
        encoding="utf-8",
    )
    snapshot = _service.read_csv_snapshot(csv_path, max_rows=10)
    assert snapshot.columns == ["pilot_id", "pilot_name", "score"]
    assert len(snapshot.rows) == 2
    assert snapshot.rows[0]["pilot_name"] == "张磊"


def test_import_sync_csv_multipart_route(tmp_path, monkeypatch):
    rag = SimpleNamespace(working_dir=str(tmp_path / "rag"))
    csv_bytes = b"pilot_id,pilot_name\n1,\xe5\xbc\xa0\xe7\xa3\x8a\n"

    async def _noop_reserve(_rag):
        return False

    async def _noop_release(_rag):
        return None

    monkeypatch.setattr(_routes, "_reserve_enqueue_slot", _noop_reserve)
    monkeypatch.setattr(_routes, "_release_enqueue_slot", _noop_release)
    monkeypatch.setattr(
        _routes,
        "probe_import_models",
        AsyncMock(return_value=(True, None)),
    )
    monkeypatch.setattr(
        _routes,
        "import_csv_file",
        AsyncMock(
            return_value=[
                _service.SqliteTableConversionResult(
                    table="pilots",
                    file_source="csv_import/csv_pilots.txt",
                    track_id="csv_test",
                    row_count=1,
                    text_chars=42,
                    status="queued",
                )
            ]
        ),
    )

    app = FastAPI()
    app.include_router(create_sqlite_import_routes(rag))
    client = TestClient(app)

    response = client.post(
        "/sqlite/import_sync",
        files={"file": ("pilots.csv", csv_bytes, "text/csv")},
        data={
            "language": "Chinese",
            "file_source_prefix": "csv_import",
            "dataset_name": "pilots",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["source_type"] == "csv"
    assert payload["results"][0]["table"] == "pilots"
    assert "sqlite_uploads" in payload["database_path"]
