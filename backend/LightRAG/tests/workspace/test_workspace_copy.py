"""Tests for workspace cloning (POST /workspaces/{id}/copy)."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Importing the routers runs an argparse pass over sys.argv at import time,
# which would otherwise choke on pytest's own arguments.
_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
try:
    from lightrag.api.routers.workspace_routes import create_workspace_routes
    from lightrag.api.workspace_service import WorkspaceService
finally:
    sys.argv = _original_argv

pytestmark = pytest.mark.offline


@pytest.fixture()
def workspace_service(tmp_path):
    registry_path = tmp_path / "workspaces_registry.json"
    registry_path.write_text(json.dumps({"workspaces": []}), encoding="utf-8")

    service = WorkspaceService(
        default_workspace="",
        working_dir=str(tmp_path),
        input_dir=str(tmp_path / "inputs"),
        rag_factory=lambda workspace: AsyncMock(workspace=workspace),
    )
    service._registry = {"workspaces": [{"id": "src", "name": "Source"}]}

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "kv_store_full_docs.json").write_text('{"doc-1": {}}', encoding="utf-8")
    (src_dir / "graph_chunk_entity_relation.graphml").write_text(
        "<graphml/>", encoding="utf-8"
    )
    src_input = tmp_path / "inputs" / "src"
    src_input.mkdir(parents=True)
    (src_input / "report.txt").write_text("scores", encoding="utf-8")
    return service


@pytest.fixture()
def client(workspace_service):
    app = FastAPI()
    app.include_router(create_workspace_routes(workspace_service))
    return TestClient(app)


def test_copy_workspace_clones_storage_and_inputs(client, workspace_service, tmp_path):
    response = client.post(
        "/workspaces/src/copy", json={"target_id": "src_b01", "name": "Branch 01"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "src_b01"
    assert payload["name"] == "Branch 01"

    copied = tmp_path / "src_b01"
    assert (copied / "kv_store_full_docs.json").read_text(encoding="utf-8") == '{"doc-1": {}}'
    assert (copied / "graph_chunk_entity_relation.graphml").exists()
    assert (tmp_path / "inputs" / "src_b01" / "report.txt").exists()
    assert any(w["id"] == "src_b01" for w in workspace_service.list_workspaces())


def test_copy_does_not_prewarm_target_instance(client, workspace_service):
    client.post("/workspaces/src/copy", json={"target_id": "src_b02"})

    # Pre-warming would initialize empty storages and clobber the copied files.
    assert "src_b02" not in workspace_service._rags


def test_copy_workspace_rejects_existing_target(client):
    assert client.post("/workspaces/src/copy", json={"target_id": "dup"}).status_code == 200

    response = client.post("/workspaces/src/copy", json={"target_id": "dup"})

    assert response.status_code == 409


def test_copy_workspace_rejects_same_source_and_target(client):
    response = client.post("/workspaces/src/copy", json={"target_id": "src"})

    assert response.status_code == 400


def test_copy_workspace_rejects_path_traversal_target(client):
    response = client.post("/workspaces/src/copy", json={"target_id": "../outside"})

    assert response.status_code == 422


def test_copy_missing_source_creates_empty_workspace(client, tmp_path):
    response = client.post("/workspaces/absent/copy", json={"target_id": "absent_b01"})

    assert response.status_code == 200
    assert (tmp_path / "absent_b01").is_dir()


def test_copy_clears_tombstone(client, workspace_service):
    workspace_service._add_tombstone("revived")

    response = client.post("/workspaces/src/copy", json={"target_id": "revived"})

    assert response.status_code == 200
    assert "revived" not in workspace_service._tombstones()
