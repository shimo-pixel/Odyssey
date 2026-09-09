"""
Workspace (task) management routes for multi-tenant LightRAG API.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from lightrag.utils import logger, validate_workspace
from ..utils_api import get_combined_auth_dependency
from ..workspace_service import WorkspaceService


class WorkspaceCreateRequest(BaseModel):
    id: str = Field(
        ...,
        description="Workspace identifier (letters, digits, underscores, hyphens)",
        min_length=1,
        max_length=64,
        examples=["task_alpha", "dom-2066450285001818113"],
    )
    name: Optional[str] = Field(
        default=None,
        description="Human-readable task name",
        max_length=128,
        examples=["Alpha Research Task"],
    )

    @field_validator("id", mode="after")
    @classmethod
    def validate_id(cls, value: str) -> str:
        workspace_id = value.strip()
        if not workspace_id:
            raise ValueError("Workspace id cannot be empty")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", workspace_id):
            raise ValueError(
                "Workspace id may only contain letters, digits, underscores, and hyphens"
            )
        validate_workspace(workspace_id)
        return workspace_id


class WorkspaceCopyRequest(BaseModel):
    target_id: str = Field(
        ...,
        description="Identifier of the new workspace (letters, digits, underscores, hyphens)",
        min_length=1,
        max_length=64,
        examples=["task_alpha_branch01"],
    )
    name: Optional[str] = Field(
        default=None,
        description="Human-readable name for the copy",
        max_length=128,
    )

    @field_validator("target_id", mode="after")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        workspace_id = value.strip()
        if not workspace_id:
            raise ValueError("Workspace id cannot be empty")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", workspace_id):
            raise ValueError(
                "Workspace id may only contain letters, digits, underscores, and hyphens"
            )
        validate_workspace(workspace_id)
        return workspace_id


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]
    default_workspace: str


def create_workspace_routes(
    workspace_service: WorkspaceService, api_key: Optional[str] = None
):
    router = APIRouter(prefix="/workspaces", tags=["workspaces"])
    combined_auth = get_combined_auth_dependency(api_key)

    @router.get(
        "",
        response_model=WorkspaceListResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def list_workspaces():
        workspaces = [
            WorkspaceResponse(
                id=w["id"],
                name=w.get("name") or w["id"],
                created_at=w.get("created_at"),
            )
            for w in workspace_service.list_workspaces()
        ]
        return WorkspaceListResponse(
            workspaces=workspaces,
            default_workspace=workspace_service.default_workspace,
        )

    @router.post(
        "",
        response_model=WorkspaceResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def create_workspace(body: WorkspaceCreateRequest):
        try:
            created = await workspace_service.create_workspace(body.id, body.name)
            return WorkspaceResponse(**created)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to create workspace: %s", exc)
            raise HTTPException(
                status_code=500, detail=f"Failed to create workspace: {exc}"
            ) from exc

    @router.post(
        "/{workspace_id}/copy",
        response_model=WorkspaceResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def copy_workspace(workspace_id: str, body: WorkspaceCopyRequest):
        source = workspace_id.strip()
        try:
            validate_workspace(source)
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", source):
                raise ValueError(
                    "Workspace id may only contain letters, digits, underscores, and hyphens"
                )
            created = await workspace_service.copy_workspace(
                source, body.target_id, body.name
            )
            return WorkspaceResponse(
                id=created["id"],
                name=created["name"],
                created_at=created.get("created_at"),
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to copy workspace %s: %s", source, exc)
            raise HTTPException(
                status_code=500, detail=f"Failed to copy workspace: {exc}"
            ) from exc

    @router.delete(
        "/{workspace_id}",
        dependencies=[Depends(combined_auth)],
    )
    async def delete_workspace(workspace_id: str):
        ws = workspace_id.strip()
        try:
            validate_workspace(ws)
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", ws):
                raise ValueError(
                    "Workspace id may only contain letters, digits, underscores, and hyphens"
                )
            await workspace_service.delete_workspace(ws)
            return {"status": "success", "workspace": ws}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to delete workspace %s: %s", ws, exc)
            raise HTTPException(
                status_code=500, detail=f"Failed to delete workspace: {exc}"
            ) from exc

    return router
