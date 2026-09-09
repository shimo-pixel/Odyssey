"""Tests for POST /workspaces id validation (DTS dom-* ids)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from lightrag.api.routers.workspace_routes import create_workspace_routes
from lightrag.api.workspace_service import WorkspaceService

pytestmark = pytest.mark.offline


def _validation_exception_handler(request: Request, exc: RequestValidationError):
    detail = []
    for error in exc.errors():
        item = dict(error)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {key: str(val) for key, val in ctx.items()}
        detail.append(item)
    return JSONResponse(status_code=422, content={"detail": detail})


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
    service._registry = {"workspaces": []}
    return service


@pytest.fixture()
def client(workspace_service):
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.include_router(create_workspace_routes(workspace_service))
    return TestClient(app)


def test_create_workspace_accepts_dom_hyphen_id(client):
    response = client.post(
        "/workspaces",
        json={"id": "dom-2066450285001818113", "name": "域知识库"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "dom-2066450285001818113"
    assert payload["name"] == "域知识库"


def test_create_workspace_rejects_path_traversal(client):
    response = client.post(
        "/workspaces",
        json={"id": "../outside", "name": "bad"},
    )

    assert response.status_code == 422
    json.dumps(response.json())


def test_create_workspace_rejects_slash_in_id(client):
    response = client.post(
        "/workspaces",
        json={"id": "bad/id", "name": "x"},
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    json.dumps(body)


def test_delete_workspace_keeps_hyphen_id(client, workspace_service):
    workspace_service._registry = {"workspaces": [{"id": "dom-123", "name": "Domain"}]}

    response = client.delete("/workspaces/dom-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace"] == "dom-123"
    assert workspace_service.list_workspaces() == []
    assert "dom-123" in workspace_service._tombstones()
