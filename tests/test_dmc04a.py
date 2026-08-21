from __future__ import annotations

from collections import Counter, defaultdict

import pytest

from dmc04a.benchmark import (
    CAPACITY,
    CASES_PER_CONDITION,
    VALUES,
    build_dataset,
    exact_token_retrieval,
    oracle_retrieval,
    query_only_answer,
    random_retrieval,
    score,
    single_attribute_retrieval,
    validate_case,
)


def _groups(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[(case["family"], case["condition"])].append(case)
    return groups


def test_dmc04a_is_deterministic_balanced_and_capacity_bounded():
    first = build_dataset()
    second = build_dataset()
    assert first == second
    assert {split: len(cases) for split, cases in first.items()} == {"train": 128, "iid": 128, "extrapolation": 112}
    for split, cases in first.items():
        for case in cases:
            validate_case(case)
            assert len(case["neural_view"]["memory"]) <= CAPACITY
        for condition_cases in _groups(cases).values():
            assert len(condition_cases) == CASES_PER_CONDITION
            assert Counter(case["oracle_view"]["answer"] for case in condition_cases) == Counter({value: 2 for value in VALUES})


def test_symbolic_oracle_retrieves_and_answers_every_case():
    dataset = build_dataset()
    for cases in dataset.values():
        assert score(cases, oracle_retrieval) == pytest.approx(1.0)
        for case in cases:
            assert oracle_retrieval(case) == case["oracle_view"]["target_record_id"]


def test_codebooks_are_disjoint_and_query_only_is_class_prior():
    dataset = build_dataset()
    for cases in dataset.values():
        assert sum(query_only_answer(case) == case["oracle_view"]["answer"] for case in cases) / len(cases) == pytest.approx(1 / 8)
        for case in cases:
            write_tokens = {token for memory in case["neural_view"]["memory"] for token in memory["write_descriptor"]["tokens"]}
            query_tokens = set(case["neural_view"]["query"]["query_descriptor"]["tokens"])
            assert not write_tokens & query_tokens
            assert "logical_key" not in str(case["neural_view"])
            assert '"answer"' not in str(case["neural_view"])
            assert case["case_id"] not in str(case["neural_view"])


def test_exact_token_control_stays_at_chance_and_single_attributes_fail_hard_negatives():
    cases = build_dataset()["extrapolation"]
    assert score(cases, exact_token_retrieval) == pytest.approx(1 / 16)
    hard = [case for case in cases if case["family"] == "hard_negative"]
    assert 1.0 - score(hard, lambda case: single_attribute_retrieval(case, "A")) >= 0.40
    assert 1.0 - score(hard, lambda case: single_attribute_retrieval(case, "B")) >= 0.40


def test_versioned_cases_have_two_versions_and_correct_oracle_semantics():
    cases = build_dataset()["extrapolation"]
    for case in cases:
        if case["family"] != "versioned":
            continue
        target = tuple(case["oracle_view"]["target_logical_key"])
        matches = [record for record in case["oracle_view"]["records"] if tuple(record["logical_key"]) == target]
        assert len(matches) == 2
        assert {record["version"] for record in matches} == {"history", "current"}
        assert oracle_retrieval(case) == case["oracle_view"]["target_record_id"]
