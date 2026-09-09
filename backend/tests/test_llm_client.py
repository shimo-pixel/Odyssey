import json

import pytest

from prds.llm.client import LLMClient, LLMStructuredOutputError


def test_parse_json_plain_object():
    payload = {"thought": "x", "action": "hold"}
    assert LLMClient._parse_json(json.dumps(payload)) == payload


def test_parse_json_markdown_fence():
    raw = 'Here is the decision:\n```json\n{"thought": "x", "action": "hold"}\n```'
    assert LLMClient._parse_json(raw)["action"] == "hold"


def test_parse_json_embedded_object():
    raw = 'Analysis complete.\n{"thought": "x", "action": "hold"}\nThanks.'
    assert LLMClient._parse_json(raw)["action"] == "hold"


def test_parse_json_empty_raises():
    with pytest.raises(LLMStructuredOutputError, match="Empty"):
        LLMClient._parse_json("   ")


def test_parse_json_non_object_raises():
    with pytest.raises(LLMStructuredOutputError, match="JSON object"):
        LLMClient._parse_json("[1, 2, 3]")
