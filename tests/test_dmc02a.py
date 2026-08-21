from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

import pytest

from dmc02a.benchmark import (
    CAPACITY,
    CASES_PER_CONDITION,
    SPLIT_SPECS,
    VALUES,
    bounded_oracle,
    build_dataset,
    build_split,
    content_hash,
    current_episode_only,
    fifo_control,
    label_counts,
    random_retention_control,
    unbounded_oracle,
    validate_case,
)


def _groups(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[(case["family"], case["condition"])].append(case)
    return groups


def _score(answerer, cases):
    return sum(answerer(case) == case["answer"] for case in cases) / len(cases)


def _primary(answerer, cases):
    groups = _groups(cases)
    components = [
        _score(answerer, groups[("mission_set", "load_256")]),
        _score(answerer, groups[("mission_set", "load_1024")]),
        _score(answerer, groups[("salience", "load_256")]),
        _score(answerer, groups[("salience", "load_1024")]),
        _score(answerer, groups[("supersession", "load_1024_current")]),
        _score(answerer, groups[("supersession", "load_1024_history")]),
        sum(_score(answerer, groups[("utility_change", f"load_1024_overlap_{overlap}")]) for overlap in (0, 25, 50, 75, 100)) / 5,
        _score(answerer, groups[("distractor_flood", "distractors_512")]),
        _score(answerer, groups[("distractor_flood", "distractors_1024")]),
    ]
    return sum(components) / len(components)


def test_dmc02a_is_deterministic_and_split_allocations_are_frozen():
    first = build_dataset()
    second = build_dataset()
    assert first == second
    assert {split: len(cases) for split, cases in first.items()} == {"train": 256, "iid": 256, "extrapolation": 480}
    for split, cases in first.items():
        assert all(case["split"] == split for case in cases)
        for _, condition_cases in _groups(cases).items():
            assert len(condition_cases) == CASES_PER_CONDITION
            assert label_counts(condition_cases) == {value: 2 for value in VALUES}


def test_oracles_solve_every_case_with_the_hard_budget():
    for cases in build_dataset().values():
        for case in cases:
            validate_case(case)
            assert unbounded_oracle(case) == case["answer"]
            assert bounded_oracle(case) == case["answer"]
            assert case["metadata"]["minimum_required_records"] <= CAPACITY


def test_current_episode_only_is_the_one_eighth_control():
    for cases in build_dataset().values():
        assert _score(current_episode_only, cases) == pytest.approx(1 / len(VALUES))
        for case in cases:
            query = case["episodes"][-1]["events"][0]
            assert set(query) == {"kind", "entity", "field", "mode", "as_of_episode"}
            assert "value" not in query and "answer" not in query and "memory_id" not in query
            assert case["case_id"] not in str(query)


def test_fifo_and_random_controls_separate_at_extrapolated_capacity():
    cases = build_split("extrapolation")
    bounded = _primary(bounded_oracle, cases)
    fifo = _primary(fifo_control, cases)
    random = _primary(random_retention_control, cases)
    assert bounded == pytest.approx(1.0)
    assert bounded - fifo >= 0.40
    assert bounded - random >= 0.40


def test_supersession_preserves_both_versions_and_utility_update_precedes_phase_b():
    cases = build_split("extrapolation")
    history = next(case for case in cases if case["family"] == "supersession" and case["condition"] == "load_1024_history")
    current = next(case for case in cases if case["family"] == "supersession" and case["condition"] == "load_1024_current")
    assert unbounded_oracle(history) == history["answer"]
    assert unbounded_oracle(current) == current["answer"]
    utility = next(case for case in cases if case["family"] == "utility_change" and case["condition"] == "load_1024_overlap_25")
    update_index = next(episode["index"] for episode in utility["episodes"] if episode["events"][0]["kind"] == "mission_update")
    first_phase_b = next(episode["index"] for episode in utility["episodes"] if episode["events"][0]["kind"] == "write" and episode["events"][0]["entity"].startswith("utility-b-"))
    assert first_phase_b > update_index
    assert utility["metadata"]["minimum_required_records"] == 16


def test_malformed_cases_fail_closed_and_content_hash_excludes_only_hidden_answer():
    case = deepcopy(build_split("train")[0])
    case["episodes"][-1]["events"][0]["value"] = "RED"
    with pytest.raises(ValueError):
        validate_case(case)
    case = deepcopy(build_split("train")[0])
    case["answer"] = VALUES[1] if case["answer"] == VALUES[0] else VALUES[0]
    assert content_hash(case) == case["content_hash"]

