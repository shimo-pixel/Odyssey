"""Reverse proxy for LightRAG WebUI + API under /lightrag."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from prds.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["lightrag-proxy"])

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


async def _proxy(request: Request, path: str) -> Response:
    settings = get_settings()
    base = settings.prds_lightrag_url.rstrip("/")
    # path is relative under /lightrag/; empty means root
    target = f"{base}/{path}" if path else f"{base}/"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    body = await request.body()

    client: httpx.AsyncClient = request.app.state.lightrag_http
    try:
        upstream = await client.request(
            request.method,
            target,
            headers=headers,
            content=body,
        )
    except httpx.RequestError as exc:
        logger.warning("LightRAG proxy error: %s", exc)
        return Response(
            content=f'{{"detail":"LightRAG unreachable: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )

    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.api_route("/lightrag", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@router.api_route("/lightrag/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def lightrag_proxy(request: Request, path: str = "") -> Response:
    return await _proxy(request, path)
