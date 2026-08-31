from __future__ import annotations

import pytest

from experiments.wildflower_predictive_authority_0_1 import design
from experiments.wildflower_predictive_authority_0_1.diagnostics import (
    failure_type_cases,
    run_engineering_profile,
)
from experiments.wildflower_predictive_authority_0_1.qualification_guard import (
    assert_seed_authorized,
    assert_seed_is_registered,
    qualification_is_locked,
)
from experiments.wildflower_predictive_authority_0_1.run_predictive_authority01 import (
    _selection,
    source_hashes,
)


def test_new_selector_namespace_and_reserved_seeds() -> None:
    assert design.selectors_are_fresh()
    starts = [
        start
        for ranges in design.selector_ranges().values()
        for start, _ in ranges.values()
    ]
    assert len(starts) == len(set(starts))
    for seed in (311, 320, 340, 341, 350, 351):
        with pytest.raises(ValueError, match="historical"):
            assert_seed_is_registered(seed)


def test_execution_is_locked_for_fresh_development_seed() -> None:
    assert qualification_is_locked()
    with pytest.raises(RuntimeError, match="locked"):
        assert_seed_authorized(360)


def test_selection_is_deterministic_and_fresh() -> None:
    first = _selection(360)
    second = _selection(360)
    assert first == second
    assert set(first) == {"training", "ordinary_test"}
    selected = [episode for group in first.values() for episodes in group.values() for episode in episodes]
    assert len(selected) == len(set(selected))


def test_profile_is_engineering_only_and_audits_missing_historical_fields() -> None:
    result = run_engineering_profile()
    assert result["scientific_seed_executed"] is False
    assert result["selector_namespace_used"] is False
    assert result["failure_type_matrix"]["case_count"] == len(failure_type_cases())
    audit = result["historical_artifact_audit"]
    assert audit["learned_only_h8_present"] is False
    assert audit["full_h8_counterfactuals_available"] is False


def test_source_hashes_cover_successor_and_fixed_numeric_dependencies() -> None:
    hashes = source_hashes()
    assert hashes["historical/probe_innovation_model.py"]
    assert hashes["historical/wildflower0/nursery1.py"]
    assert any(key.startswith("successor/") for key in hashes)
