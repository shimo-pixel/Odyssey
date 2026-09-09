"""
Federated LightRAG query routes for trusted task spaces.

Forwards queries to each domain's LightRAG `/query` or `/query/data` endpoint
in parallel and merges results. Does not import or persist remote domain data.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from lightrag.api.federated_query_service import (
    FederatedDomainTarget,
    federated_query_data,
    federated_query_text,
    load_federated_domains_from_env,
    resolve_federated_domains,
)
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.utils import get_env_value, logger


class FederatedDomainTargetRequest(BaseModel):
    domain_id: str = Field(..., description="Logical domain identifier, e.g. dom-a")
    base_url: str = Field(
        ...,
        description="LightRAG base URL for this domain, e.g. http://39.96.26.122:9621",
    )
    workspace: str = Field(
        ...,
        description="Domain workspace header value (LIGHTRAG-WORKSPACE)",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Optional Bearer token for the remote LightRAG instance",
    )
    enabled: bool = Field(default=True, description="Whether to include this domain")


class FederatedQueryRequest(BaseModel):
    query: str = Field(min_length=3, description="Natural language query")
    task_space_id: Optional[str] = Field(
        default=None,
        description="Optional task space id for audit/logging",
    )
    domains: Optional[list[FederatedDomainTargetRequest]] = Field(
        default=None,
        description=(
            "Domain LightRAG endpoints to query. "
            "If omitted, uses env FEDERATED_LIGHTRAG_DOMAINS."
        ),
    )
    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = Field(
        default="mix",
        description="Query mode forwarded to each domain LightRAG",
    )
    top_k: Optional[int] = Field(default=None, ge=1)
    chunk_top_k: Optional[int] = Field(default=None, ge=1)
    hl_keywords: list[str] = Field(default_factory=list)
    ll_keywords: list[str] = Field(default_factory=list)
    include_references: bool = Field(default=True)
    include_chunk_content: bool = Field(default=False)
    timeout_sec: Optional[float] = Field(
        default=None,
        ge=1.0,
        description="Per-domain HTTP timeout in seconds",
    )

    @field_validator("query", mode="after")
    @classmethod
    def strip_query(cls, value: str) -> str:
        return value.strip()


class FederatedQueryResponse(BaseModel):
    status: Literal["success", "partial_success", "failure"]
    query: str
    mode: str
    task_space_id: Optional[str] = None
    domains_total: int
    domains_succeeded: int
    domains_failed: int
    summary: str
    results: list[dict]
    references: list[dict] = Field(default_factory=list)


class FederatedQueryDataResponse(BaseModel):
    status: Literal["success", "partial_success", "failure"]
    message: str
    query: str
    mode: str
    task_space_id: Optional[str] = None
    domains_total: int
    domains_succeeded: int
    domains_failed: int
    data: dict
    domains: list[dict] = Field(default_factory=list)


class FederatedDomainsResponse(BaseModel):
    domains: list[FederatedDomainTargetRequest]


def _to_targets(
    items: list[FederatedDomainTargetRequest] | None,
) -> list[FederatedDomainTarget] | None:
    if items is None:
        return None
    return [
        FederatedDomainTarget(
            domain_id=item.domain_id,
            base_url=item.base_url,
            workspace=item.workspace,
            api_key=item.api_key,
            enabled=item.enabled,
        )
        for item in items
    ]


def _default_timeout(body: FederatedQueryRequest) -> float:
    if body.timeout_sec is not None:
        return body.timeout_sec
    raw = get_env_value("FEDERATED_LIGHTRAG_TIMEOUT_SEC", "120")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 120.0


def create_federated_query_routes(api_key: Optional[str] = None):
    router = APIRouter(prefix="/federated", tags=["federated"])
    combined_auth = get_combined_auth_dependency(api_key)

    @router.get(
        "/domains",
        response_model=FederatedDomainsResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def list_federated_domains():
        """List federated domain LightRAG endpoints from environment config."""
        targets = load_federated_domains_from_env()
        return FederatedDomainsResponse(
            domains=[
                FederatedDomainTargetRequest(
                    domain_id=t.domain_id,
                    base_url=t.base_url,
                    workspace=t.workspace,
                    api_key=t.api_key,
                    enabled=t.enabled,
                )
                for t in targets
            ]
        )

    @router.post(
        "/query",
        response_model=FederatedQueryResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def federated_query(body: FederatedQueryRequest):
        """
        Query all configured domain LightRAG instances in parallel and merge answers.

        Data remains on each domain; this endpoint only aggregates HTTP responses.
        """
        try:
            domains = resolve_federated_domains(_to_targets(body.domains))
            payload = await federated_query_text(
                domains,
                query=body.query,
                mode=body.mode,
                top_k=body.top_k,
                chunk_top_k=body.chunk_top_k,
                hl_keywords=body.hl_keywords,
                ll_keywords=body.ll_keywords,
                include_references=body.include_references,
                include_chunk_content=body.include_chunk_content,
                timeout_sec=_default_timeout(body),
            )
            if body.task_space_id:
                logger.info(
                    "[federated_query] task_space_id=%s domains=%s status=%s",
                    body.task_space_id,
                    len(domains),
                    payload.get("status"),
                )
            payload["task_space_id"] = body.task_space_id
            return FederatedQueryResponse(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("[federated_query] failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post(
        "/query/data",
        response_model=FederatedQueryDataResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def federated_query_structured(body: FederatedQueryRequest):
        """
        Federated variant of `/query/data` — merges entities, relationships, chunks.
        """
        try:
            domains = resolve_federated_domains(_to_targets(body.domains))
            payload = await federated_query_data(
                domains,
                query=body.query,
                mode=body.mode,
                top_k=body.top_k,
                chunk_top_k=body.chunk_top_k,
                hl_keywords=body.hl_keywords,
                ll_keywords=body.ll_keywords,
                timeout_sec=_default_timeout(body),
            )
            if body.task_space_id:
                logger.info(
                    "[federated_query/data] task_space_id=%s domains=%s status=%s",
                    body.task_space_id,
                    len(domains),
                    payload.get("status"),
                )
            payload["task_space_id"] = body.task_space_id
            return FederatedQueryDataResponse(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("[federated_query/data] failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
