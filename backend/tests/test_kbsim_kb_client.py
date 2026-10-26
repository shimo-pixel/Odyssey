"""LightRAG client behaviour the branch pipeline depends on."""

import hashlib
import asyncio
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import httpx
import pytest

from prds.config import get_settings
from prds.kb.client import LightRAGClient, doc_id_for_source, normalize_workspace_id
from tests.kbsim_fakes import mock_transport_client

LIGHTRAG_SRC = Path(__file__).resolve().parents[1] / "LightRAG"


def _client(handler) -> LightRAGClient:
    client = LightRAGClient(get_settings())
    client._client = lambda: mock_transport_client(handler)  # type: ignore[method-assign]
    return client


def test_doc_id_matches_lightrag_hash_formula():
    source = "prds_branch_state.md"
    expected = "doc-" + hashlib.md5(source.encode("utf-8")).hexdigest()
    assert doc_id_for_source(source) == expected


def test_doc_id_matches_real_lightrag_implementation():
    """The whole delete-by-id scheme breaks if LightRAG changes its hashing."""
    if str(LIGHTRAG_SRC) not in sys.path:
        sys.path.insert(0, str(LIGHTRAG_SRC))
    lightrag_utils = pytest.importorskip("lightrag.utils")

    for source in ("prds_branch_state.md", "prds_branch_baseline.md"):
        assert doc_id_for_source(source) == lightrag_utils.compute_mdhash_id(
            source, prefix="doc-"
        )


def test_normalize_workspace_id_slugifies():
    assert normalize_workspace_id("sim_abc_b01") == "sim_abc_b01"
    assert normalize_workspace_id("math kb 2024") == "math_kb_2024"
    # Nothing slug-safe survives, so a stable random id is generated instead.
    assert normalize_workspace_id("我的知识库").startswith("cat_")
    assert len(normalize_workspace_id("x" * 200)) == 64


@pytest.mark.asyncio
async def test_replace_document_deletes_previous_snapshot_first():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/documents/delete_document":
            body = json.loads(request.content)
            assert body["doc_ids"] == [doc_id_for_source("prds_branch_state.md")]
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/documents/text":
            body = json.loads(request.content)
            assert body["file_source"] == "prds_branch_state.md"
            return httpx.Response(200, json={"track_id": "t1"})
        if request.url.path.startswith("/documents/track_status/"):
            return httpx.Response(200, json={"documents": [{"status": "processed"}]})
        return httpx.Response(404)

    ok = await _client(handler).replace_document(
        "# snapshot", "prds_branch_state.md", workspace="sim_x_b01", timeout=5
    )

    assert ok is True
    assert [path for _, path in seen] == [
        "/documents/delete_document",
        "/documents/text",
        "/documents/track_status/t1",
    ]


@pytest.mark.asyncio
async def test_replace_document_survives_missing_previous_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/documents/delete_document":
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path == "/documents/text":
            return httpx.Response(200, json={"track_id": "t2"})
        return httpx.Response(200, json={"documents": [{"status": "processed"}]})

    assert await _client(handler).replace_document(
        "# snapshot", "prds_branch_state.md", workspace="sim_x_b01", timeout=5
    )


@pytest.mark.asyncio
async def test_query_data_forwards_precomputed_keywords_and_workspace():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["workspace"] = request.headers.get("LIGHTRAG-WORKSPACE")
        return httpx.Response(200, json={"data": {"entities": []}})

    await _client(handler).query_data(
        "测验难度上升",
        workspace="sim_x_b01",
        hl_keywords=["数学成绩"],
        ll_keywords=["第 1 次测验"],
    )

    assert captured["path"] == "/query/data"
    assert captured["workspace"] == "sim_x_b01"
    assert captured["body"]["hl_keywords"] == ["数学成绩"]
    assert captured["body"]["ll_keywords"] == ["第 1 次测验"]


@pytest.mark.asyncio
async def test_retrieve_context_merges_workspaces_and_truncates():
    def handler(request: httpx.Request) -> httpx.Response:
        workspace = request.headers.get("LIGHTRAG-WORKSPACE", "")
        return httpx.Response(
            200,
            json={
                "data": {
                    "entities": [
                        {"entity_name": f"E-{workspace}", "entity_type": "person", "description": "x" * 200}
                    ]
                }
            },
        )

    merged = await _client(handler).retrieve_context(
        "查询", ["ws_a", "ws_b"], max_chars=120
    )

    assert merged.endswith("…")
    assert len(merged) == 120


@pytest.mark.asyncio
async def test_retrieve_context_rejects_partial_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("LIGHTRAG-WORKSPACE") == "broken":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"data": {"chunks": [{"content": "有效上下文"}]}})

    with pytest.raises(httpx.HTTPStatusError):
        await _client(handler).retrieve_context("查询", ["broken", "healthy"])


@pytest.mark.asyncio
async def test_copy_workspace_posts_to_copy_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "sim_x_b01_kb"})

    await _client(handler).copy_workspace("kb", "sim_x_b01_kb", "策略 1 · kb")

    assert captured["path"] == "/workspaces/kb/copy"
    assert captured["body"]["target_id"] == "sim_x_b01_kb"


@pytest.mark.asyncio
async def test_wait_indexed_returns_false_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": [{"status": "processing"}]})

    ok = await _client(handler).wait_indexed(
        "t3", workspace="ws", timeout=0.05, poll_interval=0.01
    )
    assert ok is False


@pytest.mark.parametrize('timeout', [0, None])
async def test_unlimited_replacement_waits_past_old_deadline(monkeypatch, timeout):
    import prds.kb.client as client_module

    elapsed = 0.0
    polls = 0
    deadlines = []

    async def sleep(_delay):
        nonlocal elapsed
        elapsed += 301

    def record_timeout(delay):
        deadlines.append(delay)
        return asyncio.timeout(delay)

    monkeypatch.setattr(client_module, 'asyncio', SimpleNamespace(
        get_running_loop=lambda: SimpleNamespace(time=lambda: elapsed),
        timeout=record_timeout, sleep=sleep,
    ))

    def handler(request):
        nonlocal polls
        if request.url.path == '/documents/delete_document':
            return httpx.Response(200, json={'status': 'ok'})
        if request.url.path == '/documents/text':
            return httpx.Response(200, json={'track_id': 'slow-index'})
        polls += 1
        status = 'processed' if polls == 3 else 'processing'
        return httpx.Response(200, json={'documents': [{'status': status}]})

    assert await _client(handler).replace_document(
        'snapshot', 'state.md', workspace='branch', timeout=timeout,
    )
    assert elapsed == 602
    assert deadlines == [None, None, None, None]


async def test_unlimited_indexing_can_still_be_cancelled():
    polled = asyncio.Event()

    def handler(request):
        polled.set()
        return httpx.Response(200, json={'documents': [{'status': 'processing'}]})

    task = asyncio.create_task(_client(handler).wait_indexed('slow-index', timeout=0))
    await polled.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
