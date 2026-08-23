from __future__ import annotations

import pytest

from experiments.forge.project_tools import (
    bounded_state_update,
    canonical_compare,
    fixed_project_tools,
    inspect_failures,
    retrieve_overlap,
    strict_json_object,
    vote_confidence,
)


def test_strict_json_object_rejects_non_object() -> None:
    assert strict_json_object('{"x":1}') == {"x": 1}
    with pytest.raises(ValueError, match="JSON_OBJECT_REQUIRED"):
        strict_json_object('[1,2]')


def test_canonical_compare_ignores_object_key_order_only() -> None:
    assert canonical_compare({"left": {"a": 1, "b": 2}, "right": {"b": 2, "a": 1}}) is True
    assert canonical_compare({"left": [1, 2], "right": [2, 1]}) is False


def test_retrieval_is_transparent_and_deterministic() -> None:
    result = retrieve_overlap({
        "query": "red copper dax",
        "documents": [
            {"id": "b", "text": "copper turns a dax blue"},
            {"id": "a", "text": "red objects are warm"},
            {"id": "c", "text": "irrelevant"},
        ],
        "top_k": 2,
    })
    assert [x["document"]["id"] for x in result["selected"]] == ["b", "a"]
    assert [x["score"] for x in result["selected"]] == [2, 1]


def test_bounded_state_has_no_hidden_memory() -> None:
    first = bounded_state_update({"history": [], "append": {"x": 1}, "max_entries": 2})
    second = bounded_state_update({"history": first["history"], "append": {"x": 2}, "max_entries": 2})
    third = bounded_state_update({"history": second["history"], "append": {"x": 3}, "max_entries": 2})
    assert third == {"history": [{"x": 2}, {"x": 3}], "count": 2}


def test_confidence_fails_closed_on_tie() -> None:
    tied = vote_confidence({"votes": ["A", "B"]})
    assert tied["status"] == "TIE"
    assert tied["prediction"] is None
    winner = vote_confidence({"votes": ["A", "A", "B"]})
    assert winner["status"] == "UNIQUE_WINNER"
    assert winner["prediction"] == "A"
    assert winner["confidence"] == pytest.approx(2 / 3)


def test_failure_inspector_has_no_file_access_contract() -> None:
    rows = [
        {"failure_class": "INTERFACE_FAILURE", "tools": ["strict_json"], "id": 1},
        {"failure_class": "RESOURCE_FAILURE", "tools": [], "id": 2},
    ]
    result = inspect_failures({"rows": rows, "failure_class": "INTERFACE_FAILURE", "limit": 10})
    assert result["match_count"] == 1
    assert result["matches"][0]["id"] == 1


def test_fixed_catalog_is_small_and_explicit() -> None:
    tools = fixed_project_tools()
    assert {t.name for t in tools} == {
        "strict_json",
        "canonical_compare",
        "retrieve_overlap",
        "bounded_state",
        "vote_confidence",
        "inspect_failures",
    }
    assert all(t.cost == 1 for t in tools)
