from __future__ import annotations

from copy import deepcopy

import pytest

from dmc00.benchmark import (
    VALUES,
    build_dataset,
    build_split,
    current_episode_only,
    ledger_entries,
    oracle_answer,
    validate_case,
)


def test_dmc00_is_deterministic_and_balanced() -> None:
    first = build_split("train")
    second = build_split("train")
    assert first == second
    for family_condition in {(case["family"], case["condition"]) for case in first}:
        cases = [case for case in first if (case["family"], case["condition"]) == family_condition]
        assert len(cases) == 16
        assert {value: sum(case["answer"] == value for case in cases) for value in VALUES} == {value: 2 for value in VALUES}


def test_dmc00_oracle_handles_current_and_history() -> None:
    dataset = build_dataset()
    history = next(case for case in dataset["train"] if case["family"] == "supersession" and case["query"]["mode"] == "history")
    current = next(case for case in dataset["train"] if case["family"] == "supersession" and case["query"]["mode"] == "current")
    assert oracle_answer(history) == history["metadata"]["original_value"]
    assert oracle_answer(current) == current["metadata"]["current_value"]
    entries = ledger_entries(history)
    assert len(entries) == 2
    assert entries[1].supersedes == entries[0].memory_id


def test_current_episode_only_is_chance_control() -> None:
    cases = build_split("iid")
    assert sum(current_episode_only(case) == case["answer"] for case in cases) / len(cases) == pytest.approx(1 / len(VALUES))
    for case in cases:
        query = case["episodes"][-1]["events"][0]
        assert set(query) == {"kind", "entity", "field", "mode", "as_of_episode"}
        assert "value" not in query and "answer" not in query and "memory_id" not in query


def test_dmc00_rejects_malformed_cases() -> None:
    case = deepcopy(build_split("train")[0])
    case["episodes"][-1]["events"][0]["value"] = "RED"
    with pytest.raises(ValueError):
        validate_case(case)
