from __future__ import annotations

import pytest

from experiments.wildflower_predictive_authority_0_1.diagnostics import (
    degenerate_nontriviality_checks,
)
from experiments.wildflower_predictive_authority_0_1.gates import (
    classify_h8_origin,
    evaluate_gates,
    nontriviality,
)


def _origin(
    episode: int,
    step: int,
    learned_h8: float,
    gated_h8: float,
) -> dict[str, object]:
    rows: dict[str, list[dict[str, object]]] = {}
    for horizon in (1, 8, 32):
        row: list[dict[str, object]] = []
        for offset in range(horizon):
            learned = learned_h8 if horizon == 8 else 0.8
            gated = gated_h8 if horizon == 8 else (0.9 if horizon == 1 else 0.8)
            row.append(
                {
                    "offset": offset,
                    "null_prediction": [0.0] * 6,
                    "learned_only_prediction": [0.1] * 6,
                    "gated_prediction": [0.05] * 6,
                    "target_evaluator_only": [0.2] * 6,
                    "innovation_score": 0.5,
                    "null_local_error_evaluator_only": 1.0,
                    "learned_only_local_error_evaluator_only": learned,
                    "gated_local_error_evaluator_only": gated,
                    "authority": 0.2,
                    "clipping_fraction": 0.0,
                }
            )
        rows[str(horizon)] = row
    return {
        "episode_seed_evaluator_only": episode,
        "step": step,
        "event_locations_evaluator_only": [step],
        "rollout_horizons": rows,
    }


def test_exact_subset_formulas_and_classification() -> None:
    origins = [
        _origin(7, index, 0.8, 0.9) for index in range(30)
    ] + [_origin(7, index + 30, 1.2, 0.9) for index in range(30)]
    result = evaluate_gates(origins)
    assert result["gates"]["h8_useful_learner_capture"]
    assert result["gates"]["h8_worse_learned_protection"]
    assert result["h8_useful_learner"]["capture_fraction"] == 0.5
    assert classify_h8_origin(origins[0]) == "MODEL_GOOD_POLICY_GOOD"
    assert classify_h8_origin(origins[-1]) == "MODEL_BAD_POLICY_PROTECTED"


def test_useful_capture_below_threshold_fails() -> None:
    origins = [_origin(7, index, 0.8, 0.95) for index in range(30)]
    result = evaluate_gates(origins)
    assert result["h8_useful_learner"]["capture_fraction"] == pytest.approx(0.25)
    assert not result["gates"]["h8_useful_learner_capture"]


def test_observed_361_capture_fraction_fails() -> None:
    observed = 0.09203745816983593
    gated_h8 = 1.0 - observed * (1.0 - 0.8)
    origins = [_origin(7, index, 0.8, gated_h8) for index in range(30)]
    result = evaluate_gates(origins)
    assert result["h8_useful_learner"]["capture_fraction"] == pytest.approx(observed)
    assert not result["gates"]["h8_useful_learner_capture"]


def test_negative_captured_gain_is_retained_and_fails() -> None:
    origins = [_origin(7, index, 0.8, 1.1) for index in range(30)]
    result = evaluate_gates(origins)
    assert result["h8_useful_learner"]["captured_gain_sum"] < 0.0
    assert result["h8_useful_learner"]["capture_fraction"] < 0.0
    assert not result["gates"]["h8_useful_learner_capture"]


def test_zero_available_gain_fails_closed() -> None:
    origins = [_origin(7, index, 1.0, 0.9) for index in range(30)]
    result = evaluate_gates(origins)
    assert result["h8_useful_learner"]["origins"] == 0
    assert result["h8_useful_learner"]["available_gain_sum"] == 0.0
    assert result["h8_useful_learner"]["capture_fraction"] is None
    assert not result["gates"]["h8_useful_learner_capture"]


def test_empty_denominators_fail_closed() -> None:
    result = evaluate_gates([])
    assert result["passed"] is False
    assert nontriviality([])["passed"] is False


def test_degenerate_authority_is_rejected() -> None:
    checks = degenerate_nontriviality_checks()
    assert checks["NULL_ONLY"]["collapse_rejected"]
    assert checks["AUTHORITY_EPSILON_EVERYWHERE"]["collapse_rejected"]
    assert checks["H1_ONLY_H8_ZERO"]["collapse_rejected"]
    assert checks["PERMANENTLY_CAPPED_NEAR_ZERO"]["collapse_rejected"]
    assert checks["EASIEST_MODE_ONLY"]["mode_concentration_warning"]
