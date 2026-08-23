from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.forge.model_broker import validate_request
from experiments.forge.model_tools import make_broker_text_tool


ALLOWED = {"llama3.1:8b"}


def valid_request() -> dict:
    return {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "hello"},
        ],
        "format": "json",
        "options": {"temperature": 0, "seed": 1, "num_predict": 64},
    }


def test_broker_accepts_only_narrow_chat_contract() -> None:
    out = validate_request(valid_request(), ALLOWED)
    assert out["model"] == "llama3.1:8b"
    assert out["stream"] is False
    assert out["format"] == "json"


@pytest.mark.parametrize("extra", [
    {"tools": []},
    {"url": "http://example.com"},
    {"path": "/etc/passwd"},
    {"command": ["sh", "-c", "id"]},
])
def test_broker_rejects_extra_capabilities(extra: dict) -> None:
    req = valid_request()
    req.update(extra)
    with pytest.raises(ValueError, match="unexpected_request_keys"):
        validate_request(req, ALLOWED)


def test_broker_rejects_unapproved_model() -> None:
    req = valid_request()
    req["model"] = "some-other-model"
    with pytest.raises(ValueError, match="model_not_allowed"):
        validate_request(req, ALLOWED)


def test_broker_rejects_remote_schema_refs() -> None:
    req = valid_request()
    req["format"] = {
        "type": "object",
        "properties": {"x": {"$ref": "https://example.com/schema.json"}},
    }
    with pytest.raises(ValueError, match="remote_schema_ref_forbidden"):
        validate_request(req, ALLOWED)


def test_broker_rejects_excessive_generation_budget() -> None:
    req = valid_request()
    req["options"]["num_predict"] = 100000
    with pytest.raises(ValueError, match="num_predict_out_of_range"):
        validate_request(req, ALLOWED)


def test_model_tool_is_fixed_capability_and_requires_text(tmp_path: Path) -> None:
    tool = make_broker_text_tool(
        name="model_fixed",
        socket_path=tmp_path / "missing.sock",
        model="llama3.1:8b",
        system_prompt="Return JSON only.",
        seed=1,
        num_predict=32,
    )
    assert tool.input_kind == "text"
    assert tool.output_kind == "text"
    assert tool.cost == 4
    with pytest.raises(TypeError, match="requires text input"):
        tool.apply({"prompt": "hidden target should not be accepted"})
