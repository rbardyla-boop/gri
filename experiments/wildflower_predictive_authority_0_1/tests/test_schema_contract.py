from __future__ import annotations

import inspect

import pytest

from experiments.wildflower_predictive_authority_0_1.authority import AuthorityContext
from experiments.wildflower_predictive_authority_0_1.gates import classify_h8_origin
from experiments.wildflower_predictive_authority_0_1.trace import (
    ERROR_FIELD_BY_PATH,
    GATED_LOCAL_ERROR_FIELD,
    LEARNED_ONLY_LOCAL_ERROR_FIELD,
    LEGACY_LEARNED_LOCAL_ERROR_FIELD,
    NULL_LOCAL_ERROR_FIELD,
    ROLLOUT_STEP_FIELDS,
    RolloutStep,
    rollout_step_to_dict,
    validate_rollout_step_payload,
)


def _rollout_step(learned_error: float = 0.8, gated_error: float = 0.9) -> RolloutStep:
    vector = (0.0,) * 6
    return RolloutStep(
        offset=0,
        null_prediction=vector,
        learned_only_prediction=(0.1,) * 6,
        gated_prediction=(0.05,) * 6,
        target_evaluator_only=(0.2,) * 6,
        innovation_score=0.5,
        authority=0.2,
        null_local_error_evaluator_only=1.0,
        learned_only_local_error_evaluator_only=learned_error,
        gated_local_error_evaluator_only=gated_error,
        clipping_fraction=0.0,
    )


def _origin(learned_error: float, gated_error: float) -> dict[str, object]:
    rows: dict[str, list[dict[str, object]]] = {}
    for horizon in (1, 8, 32):
        row = rollout_step_to_dict(_rollout_step(
            learned_error if horizon == 8 else 0.8,
            gated_error if horizon == 8 else 0.8,
        ))
        rows[str(horizon)] = [
            {**row, "offset": offset} for offset in range(horizon)
        ]
    return {
        "episode_seed_evaluator_only": 360,
        "step": 14,
        "event_locations_evaluator_only": [],
        "rollout_horizons": rows,
    }


def test_producer_emits_the_canonical_learned_only_error_field() -> None:
    payload = rollout_step_to_dict(_rollout_step())

    assert LEARNED_ONLY_LOCAL_ERROR_FIELD in payload
    assert LEGACY_LEARNED_LOCAL_ERROR_FIELD not in payload
    assert set(payload) == ROLLOUT_STEP_FIELDS
    assert ERROR_FIELD_BY_PATH == {
        "null": NULL_LOCAL_ERROR_FIELD,
        "learned_only": LEARNED_ONLY_LOCAL_ERROR_FIELD,
        "gated": GATED_LOCAL_ERROR_FIELD,
    }


def test_gate_classifier_consumes_the_canonical_field() -> None:
    protected = _origin(learned_error=1.2, gated_error=1.0)
    assert classify_h8_origin(protected) == "MODEL_BAD_POLICY_PROTECTED"

    useful = _origin(learned_error=0.8, gated_error=0.9)
    assert classify_h8_origin(useful) == "MODEL_GOOD_POLICY_GOOD"


def test_retired_alias_is_rejected_by_validator_and_classifier() -> None:
    payload = rollout_step_to_dict(_rollout_step())
    payload[LEGACY_LEARNED_LOCAL_ERROR_FIELD] = payload.pop(
        LEARNED_ONLY_LOCAL_ERROR_FIELD
    )

    with pytest.raises(ValueError, match="deprecated"):
        validate_rollout_step_payload(payload)

    origin = _origin(learned_error=1.2, gated_error=1.0)
    terminal = origin["rollout_horizons"]["8"][-1]
    terminal[LEGACY_LEARNED_LOCAL_ERROR_FIELD] = terminal.pop(
        LEARNED_ONLY_LOCAL_ERROR_FIELD
    )
    with pytest.raises(ValueError, match="deprecated"):
        classify_h8_origin(origin)


def test_producer_and_consumer_share_one_exact_field_set() -> None:
    payload = rollout_step_to_dict(_rollout_step())
    validate_rollout_step_payload(payload)

    assert set(payload) == ROLLOUT_STEP_FIELDS
    assert ERROR_FIELD_BY_PATH["learned_only"] in ROLLOUT_STEP_FIELDS
    assert ERROR_FIELD_BY_PATH["learned_only"] == (
        "learned_only_local_error_evaluator_only"
    )


def test_authority_context_contains_no_evaluator_truth() -> None:
    names = tuple(inspect.signature(AuthorityContext).parameters)

    assert all("target" not in name for name in names)
    assert all("error" not in name for name in names)
    assert all("truth" not in name for name in names)
