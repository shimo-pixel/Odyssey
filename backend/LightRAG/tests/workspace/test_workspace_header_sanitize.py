"""Tests for HTTP workspace header normalization."""

import pytest

from lightrag.api.workspace_service import (
    decode_workspace_b64,
    sanitize_workspace_header,
)

pytestmark = pytest.mark.offline


def test_preserves_chinese_task_name():
    assert sanitize_workspace_header("飞行员优选2") == "飞行员优选2"


def test_preserves_ascii_task_id():
    assert sanitize_workspace_header("task_id_2") == "task_id_2"


def test_strips_surrounding_whitespace():
    assert sanitize_workspace_header("  飞行员优选2  ") == "飞行员优选2"


def test_rejects_path_traversal():
    with pytest.raises(ValueError):
        sanitize_workspace_header("../etc")


def test_repairs_latin1_mojibake():
    mojibake = "飞行员优选2".encode("utf-8").decode("latin-1")
    assert sanitize_workspace_header(mojibake) == "飞行员优选2"


def test_decodes_b64_workspace_header():
    import base64

    encoded = base64.b64encode("飞行员优选2".encode("utf-8")).decode("ascii")
    assert decode_workspace_b64(encoded) == "飞行员优选2"
