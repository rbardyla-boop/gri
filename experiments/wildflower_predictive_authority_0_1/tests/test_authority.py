from __future__ import annotations

import inspect

import pytest

from experiments.wildflower_predictive_authority_0_1.authority import (
    AuthorityContext,
    authority_for,
    oracle_authority,
)


def _context(horizon: int = 8, disagreement: float = 0.2) -> AuthorityContext:
    return AuthorityContext(
        rollout_horizon=horizon,
        horizon_step=0,
        current_authority=0.9,
        delayed_authority=0.9,
        innovation_score=0.6,
        disagreement=disagreement,
        instability=0.1,
        residual_history=0.5,
        saturation_duration=0,
        state_change=0.2,
        recurrence_sensitivity=0.2,
    )


def test_authority_context_has_no_evaluator_truth_fields() -> None:
    names = tuple(inspect.signature(AuthorityContext).parameters)
    assert all("target" not in name for name in names)
    assert all("error" not in name for name in names)
    assert all("truth" not in name for name in names)


def test_null_and_learned_controls_are_exact() -> None:
    context = _context()
    assert authority_for("P0_NULL_ONLY", context) == 0.0
    assert authority_for("P1_LEARNED_ONLY", context) == 1.0


def test_horizon_diagnostic_is_more_conservative_at_longer_horizons() -> None:
    h1 = authority_for("P5_HORIZON_AWARE_DIAGNOSTIC", _context(1))
    h8 = authority_for("P5_HORIZON_AWARE_DIAGNOSTIC", _context(8))
    h32 = authority_for("P5_HORIZON_AWARE_DIAGNOSTIC", _context(32))
    assert h1 > h8 > h32


def test_disagreement_gating_reduces_authority_without_truth() -> None:
    low = authority_for("DISAGREEMENT_GATED", _context(disagreement=0.1))
    high = authority_for("DISAGREEMENT_GATED", _context(disagreement=0.9))
    assert low > high


def test_oracle_is_separate_and_rejects_mechanism_context() -> None:
    assert oracle_authority(1.0, 0.9) == 1.0
    assert oracle_authority(0.9, 1.0) == 0.0
    with pytest.raises(ValueError, match="oracle"):
        authority_for("P6_ORACLE_UPPER_BOUND", _context())
