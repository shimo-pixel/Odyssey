"""Tests for federated LightRAG query orchestration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from lightrag.api.federated_query_service import (
    FederatedDomainTarget,
    merge_federated_data_results,
    merge_federated_text_results,
    parse_federated_domain_targets,
    FederatedDomainQueryResult,
    federated_query_text,
)


def test_parse_federated_domain_targets_from_json_string():
    raw = json.dumps(
        [
            {
                "domain_id": "dom-a",
                "base_url": "http://127.0.0.1:9621",
                "workspace": "dom-a-ws",
            },
            {
                "domain_id": "dom-b",
                "base_url": "http://127.0.0.1:9622/",
                "workspace": "dom-b-ws",
                "enabled": False,
            },
        ]
    )
    targets = parse_federated_domain_targets(raw)
    assert len(targets) == 2
    assert targets[0].domain_id == "dom-a"
    assert targets[1].enabled is False


def test_merge_federated_text_results_partial_success():
    results = [
        FederatedDomainQueryResult(
            domain_id="dom-a",
            base_url="http://a",
            workspace="ws-a",
            status="success",
            response="Answer from A",
            references=[{"reference_id": "1", "file_path": "a.txt"}],
        ),
        FederatedDomainQueryResult(
            domain_id="dom-b",
            base_url="http://b",
            workspace="ws-b",
            status="failure",
            error="timeout",
        ),
    ]
    merged = merge_federated_text_results(results)
    assert merged["status"] == "partial_success"
    assert merged["domains_succeeded"] == 1
    assert merged["domains_failed"] == 1
    assert "【dom-a】" in merged["summary"]
    assert merged["references"][0]["domain_id"] == "dom-a"
    assert merged["references"][0]["reference_id"] == "dom-a:1"


def test_merge_federated_data_results_tags_domain_id():
    results = [
        FederatedDomainQueryResult(
            domain_id="dom-a",
            base_url="http://a",
            workspace="ws-a",
            status="success",
            data={
                "entities": [{"entity_name": "Pilot A"}],
                "relationships": [{"src_id": "A", "tgt_id": "B"}],
                "chunks": [{"chunk_id": "c1", "content": "text"}],
                "references": [{"reference_id": "r1", "file_path": "f.txt"}],
            },
        )
    ]
    merged = merge_federated_data_results(results)
    assert merged["status"] == "success"
    assert merged["data"]["entities"][0]["domain_id"] == "dom-a"
    assert merged["data"]["entities"][0]["entity_name"] == "dom-a:Pilot A"
    assert merged["data"]["references"][0]["reference_id"] == "dom-a:r1"


@pytest.mark.asyncio
async def test_federated_query_text_parallel():
    domains = [
        FederatedDomainTarget("dom-a", "http://127.0.0.1:9621", "ws-a"),
        FederatedDomainTarget("dom-b", "http://127.0.0.1:9622", "ws-b"),
    ]

    async def fake_query(target, **kwargs):
        return FederatedDomainQueryResult(
            domain_id=target.domain_id,
            base_url=target.base_url,
            workspace=target.workspace,
            status="success",
            http_status=200,
            response=f"answer-{target.domain_id}",
            references=[],
        )

    with patch(
        "lightrag.api.federated_query_service.query_domain_text",
        new=AsyncMock(side_effect=fake_query),
    ):
        payload = await federated_query_text(domains, query="who is pilot")

    assert payload["domains_total"] == 2
    assert payload["domains_succeeded"] == 2
    assert "dom-a" in payload["summary"]
    assert "dom-b" in payload["summary"]
