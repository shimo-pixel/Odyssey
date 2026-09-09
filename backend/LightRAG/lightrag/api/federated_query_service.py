"""
Federated LightRAG query orchestration for trusted task spaces.

Queries stay on each domain's LightRAG deployment; this module only forwards
requests and merges responses — no cross-domain data import or local indexing.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from lightrag.utils import get_env_value, logger

_DEFAULT_QUERY_TIMEOUT_SEC = 120.0


@dataclass(frozen=True)
class FederatedDomainTarget:
    domain_id: str
    base_url: str
    workspace: str
    api_key: str | None = None
    enabled: bool = True

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def validate(self) -> None:
        if not self.domain_id or not self.domain_id.strip():
            raise ValueError("domain_id is required for each federated target")
        if not self.workspace or not self.workspace.strip():
            raise ValueError(
                f"workspace is required for federated domain '{self.domain_id}'"
            )
        parsed = urlparse(self.normalized_base_url())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Invalid base_url for domain '{self.domain_id}': {self.base_url!r}"
            )


@dataclass
class FederatedDomainQueryResult:
    domain_id: str
    base_url: str
    workspace: str
    status: str
    http_status: int | None = None
    response: str | None = None
    references: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None


def parse_federated_domain_targets(raw: str | list[dict[str, Any]] | None) -> list[FederatedDomainTarget]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        payload = json.loads(text)
    else:
        payload = raw
    if not isinstance(payload, list):
        raise ValueError("Federated domain config must be a JSON array")
    targets: list[FederatedDomainTarget] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each federated domain entry must be an object")
        target = FederatedDomainTarget(
            domain_id=str(item.get("domain_id", "")).strip(),
            base_url=str(item.get("base_url", "")).strip(),
            workspace=str(item.get("workspace", "")).strip(),
            api_key=(str(item["api_key"]).strip() if item.get("api_key") else None),
            enabled=bool(item.get("enabled", True)),
        )
        target.validate()
        targets.append(target)
    return targets


def load_federated_domains_from_env() -> list[FederatedDomainTarget]:
    raw = get_env_value("FEDERATED_LIGHTRAG_DOMAINS", "")
    if not raw:
        return []
    return parse_federated_domain_targets(str(raw))


def resolve_federated_domains(
    request_domains: list[FederatedDomainTarget] | None,
) -> list[FederatedDomainTarget]:
    if request_domains:
        resolved = list(request_domains)
    else:
        resolved = load_federated_domains_from_env()
    if not resolved:
        raise ValueError(
            "No federated LightRAG domains configured. "
            "Set FEDERATED_LIGHTRAG_DOMAINS or pass 'domains' in the request body."
        )
    active = [d for d in resolved if d.enabled]
    if not active:
        raise ValueError("All federated domains are disabled")
    for target in active:
        target.validate()
    return active


def _build_query_payload(
    *,
    query: str,
    mode: str,
    top_k: int | None,
    chunk_top_k: int | None,
    hl_keywords: list[str],
    ll_keywords: list[str],
    include_references: bool,
    include_chunk_content: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "query": query.strip(),
        "mode": mode,
        "hl_keywords": hl_keywords or [],
        "ll_keywords": ll_keywords or [],
    }
    if top_k is not None:
        body["top_k"] = top_k
    if chunk_top_k is not None:
        body["chunk_top_k"] = chunk_top_k
    body["include_references"] = include_references
    body["include_chunk_content"] = include_chunk_content
    return body


def _auth_headers(target: FederatedDomainTarget) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "LIGHTRAG-WORKSPACE": target.workspace,
    }
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"
    return headers


async def _post_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    response = await client.post(url, headers=headers, json=body)
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    return response.status_code, payload


async def query_domain_text(
    target: FederatedDomainTarget,
    *,
    query_body: dict[str, Any],
    timeout_sec: float = _DEFAULT_QUERY_TIMEOUT_SEC,
) -> FederatedDomainQueryResult:
    url = f"{target.normalized_base_url()}/query"
    result = FederatedDomainQueryResult(
        domain_id=target.domain_id,
        base_url=target.normalized_base_url(),
        workspace=target.workspace,
        status="failure",
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            status_code, payload = await _post_json(
                client,
                url=url,
                headers=_auth_headers(target),
                body=query_body,
            )
        result.http_status = status_code
        if status_code != 200 or not isinstance(payload, dict):
            result.error = (
                payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            )
            result.message = f"HTTP {status_code} from domain '{target.domain_id}'"
            return result
        result.status = "success"
        result.response = str(payload.get("response", ""))
        refs = payload.get("references")
        result.references = refs if isinstance(refs, list) else []
        result.message = "ok"
        return result
    except Exception as exc:
        logger.warning(
            "[federated_query] domain=%s url=%s failed: %s",
            target.domain_id,
            url,
            exc,
        )
        result.error = str(exc)
        result.message = f"Request failed for domain '{target.domain_id}'"
        return result


async def query_domain_data(
    target: FederatedDomainTarget,
    *,
    query_body: dict[str, Any],
    timeout_sec: float = _DEFAULT_QUERY_TIMEOUT_SEC,
) -> FederatedDomainQueryResult:
    url = f"{target.normalized_base_url()}/query/data"
    body = dict(query_body)
    body.pop("include_references", None)
    body.pop("include_chunk_content", None)

    result = FederatedDomainQueryResult(
        domain_id=target.domain_id,
        base_url=target.normalized_base_url(),
        workspace=target.workspace,
        status="failure",
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            status_code, payload = await _post_json(
                client,
                url=url,
                headers=_auth_headers(target),
                body=body,
            )
        result.http_status = status_code
        if status_code != 200 or not isinstance(payload, dict):
            result.error = (
                payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            )
            result.message = f"HTTP {status_code} from domain '{target.domain_id}'"
            return result
        result.status = "success" if payload.get("status") == "success" else "failure"
        data = payload.get("data")
        result.data = data if isinstance(data, dict) else {}
        meta = payload.get("metadata")
        result.metadata = meta if isinstance(meta, dict) else {}
        result.message = str(payload.get("message", ""))
        if result.status != "success":
            result.error = result.message or "domain query/data returned failure"
        return result
    except Exception as exc:
        logger.warning(
            "[federated_query/data] domain=%s url=%s failed: %s",
            target.domain_id,
            url,
            exc,
        )
        result.error = str(exc)
        result.message = f"Request failed for domain '{target.domain_id}'"
        return result


def _tag_items(items: list[Any], *, domain_id: str, id_field: str | None = None) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["domain_id"] = domain_id
        if id_field and id_field in row and row[id_field] is not None:
            row[id_field] = f"{domain_id}:{row[id_field]}"
        tagged.append(row)
    return tagged


def merge_federated_text_results(results: list[FederatedDomainQueryResult]) -> dict[str, Any]:
    succeeded = [r for r in results if r.status == "success" and r.response]
    failed = [r for r in results if r.status != "success"]
    summary_parts = [
        f"【{item.domain_id}】\n{item.response.strip()}"
        for item in succeeded
        if item.response and item.response.strip()
    ]
    all_references: list[dict[str, Any]] = []
    for item in succeeded:
        for ref in item.references:
            if not isinstance(ref, dict):
                continue
            tagged = dict(ref)
            tagged["domain_id"] = item.domain_id
            ref_id = tagged.get("reference_id")
            if ref_id is not None:
                tagged["reference_id"] = f"{item.domain_id}:{ref_id}"
            all_references.append(tagged)

    overall_status = "success"
    if succeeded and failed:
        overall_status = "partial_success"
    elif not succeeded:
        overall_status = "failure"

    return {
        "status": overall_status,
        "domains_total": len(results),
        "domains_succeeded": len(succeeded),
        "domains_failed": len(failed),
        "summary": "\n\n".join(summary_parts),
        "results": [
            {
                "domain_id": r.domain_id,
                "base_url": r.base_url,
                "workspace": r.workspace,
                "status": r.status,
                "http_status": r.http_status,
                "response": r.response,
                "references": r.references,
                "message": r.message,
                "error": r.error,
            }
            for r in results
        ],
        "references": all_references,
    }


def merge_federated_data_results(results: list[FederatedDomainQueryResult]) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    per_domain: list[dict[str, Any]] = []

    succeeded = 0
    for item in results:
        per_domain.append(
            {
                "domain_id": item.domain_id,
                "base_url": item.base_url,
                "workspace": item.workspace,
                "status": item.status,
                "http_status": item.http_status,
                "message": item.message,
                "error": item.error,
                "metadata": item.metadata or {},
            }
        )
        if item.status != "success" or not item.data:
            continue
        succeeded += 1
        data = item.data
        entities.extend(
            _tag_items(data.get("entities") or [], domain_id=item.domain_id, id_field="entity_name")
        )
        relationships.extend(
            _tag_items(data.get("relationships") or [], domain_id=item.domain_id)
        )
        chunks.extend(_tag_items(data.get("chunks") or [], domain_id=item.domain_id, id_field="chunk_id"))
        references.extend(
            _tag_items(data.get("references") or [], domain_id=item.domain_id, id_field="reference_id")
        )

    failed = len(results) - succeeded
    if succeeded and failed:
        status = "partial_success"
    elif succeeded:
        status = "success"
    else:
        status = "failure"

    return {
        "status": status,
        "message": (
            f"Federated query/data finished: {succeeded} succeeded, {failed} failed."
        ),
        "domains_total": len(results),
        "domains_succeeded": succeeded,
        "domains_failed": failed,
        "data": {
            "entities": entities,
            "relationships": relationships,
            "chunks": chunks,
            "references": references,
        },
        "domains": per_domain,
    }


async def federated_query_text(
    domains: list[FederatedDomainTarget],
    *,
    query: str,
    mode: str = "mix",
    top_k: int | None = None,
    chunk_top_k: int | None = None,
    hl_keywords: list[str] | None = None,
    ll_keywords: list[str] | None = None,
    include_references: bool = True,
    include_chunk_content: bool = False,
    timeout_sec: float = _DEFAULT_QUERY_TIMEOUT_SEC,
) -> dict[str, Any]:
    body = _build_query_payload(
        query=query,
        mode=mode,
        top_k=top_k,
        chunk_top_k=chunk_top_k,
        hl_keywords=hl_keywords or [],
        ll_keywords=ll_keywords or [],
        include_references=include_references,
        include_chunk_content=include_chunk_content,
    )
    tasks = [
        query_domain_text(target, query_body=body, timeout_sec=timeout_sec)
        for target in domains
    ]
    results = await asyncio.gather(*tasks)
    merged = merge_federated_text_results(list(results))
    merged["query"] = query.strip()
    merged["mode"] = mode
    return merged


async def federated_query_data(
    domains: list[FederatedDomainTarget],
    *,
    query: str,
    mode: str = "mix",
    top_k: int | None = None,
    chunk_top_k: int | None = None,
    hl_keywords: list[str] | None = None,
    ll_keywords: list[str] | None = None,
    timeout_sec: float = _DEFAULT_QUERY_TIMEOUT_SEC,
) -> dict[str, Any]:
    body = _build_query_payload(
        query=query,
        mode=mode,
        top_k=top_k,
        chunk_top_k=chunk_top_k,
        hl_keywords=hl_keywords or [],
        ll_keywords=ll_keywords or [],
        include_references=True,
        include_chunk_content=False,
    )
    tasks = [
        query_domain_data(target, query_body=body, timeout_sec=timeout_sec)
        for target in domains
    ]
    results = await asyncio.gather(*tasks)
    merged = merge_federated_data_results(list(results))
    merged["query"] = query.strip()
    merged["mode"] = mode
    return merged
