"""Replayable predictive-authority trace schema.

The evaluator-only target and error fields are explicitly named.  Mechanism
policies consume only the machine-native signals in ``AuthorityContext``.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import math


NULL_LOCAL_ERROR_FIELD = "null_local_error_evaluator_only"
LEARNED_ONLY_LOCAL_ERROR_FIELD = "learned_only_local_error_evaluator_only"
GATED_LOCAL_ERROR_FIELD = "gated_local_error_evaluator_only"
LEGACY_LEARNED_LOCAL_ERROR_FIELD = "learned_local_error_evaluator_only"

ERROR_FIELD_BY_PATH = {
    "null": NULL_LOCAL_ERROR_FIELD,
    "learned_only": LEARNED_ONLY_LOCAL_ERROR_FIELD,
    "gated": GATED_LOCAL_ERROR_FIELD,
}

ROLLOUT_STEP_FIELDS = frozenset(
    {
        "offset",
        "null_prediction",
        "learned_only_prediction",
        "gated_prediction",
        "target_evaluator_only",
        "innovation_score",
        "authority",
        NULL_LOCAL_ERROR_FIELD,
        LEARNED_ONLY_LOCAL_ERROR_FIELD,
        GATED_LOCAL_ERROR_FIELD,
        "clipping_fraction",
    }
)


def _finite(values: tuple[float, ...], label: str) -> None:
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError(f"{label} contains NaN or Inf")


def _vector(values: tuple[float, ...] | list[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    _finite(result, "prediction vector")
    return result


@dataclass(frozen=True)
class RolloutStep:
    offset: int
    null_prediction: tuple[float, ...]
    learned_only_prediction: tuple[float, ...]
    gated_prediction: tuple[float, ...]
    target_evaluator_only: tuple[float, ...]
    innovation_score: float
    authority: float
    null_local_error_evaluator_only: float
    learned_only_local_error_evaluator_only: float
    gated_local_error_evaluator_only: float
    clipping_fraction: float

    def validate(self) -> None:
        vectors = (
            self.null_prediction,
            self.learned_only_prediction,
            self.gated_prediction,
            self.target_evaluator_only,
        )
        if not all(len(vector) == 6 for vector in vectors):
            raise ValueError("rollout vectors must contain six coordinates")
        for vector in vectors:
            _finite(vector, "rollout vector")
        _finite(
            (
                self.innovation_score,
                self.authority,
                self.null_local_error_evaluator_only,
                self.learned_only_local_error_evaluator_only,
                self.gated_local_error_evaluator_only,
                self.clipping_fraction,
            ),
            "rollout step",
        )
        if not 0.0 <= self.authority <= 1.0:
            raise ValueError("rollout authority outside [0, 1]")
        if not 0.0 <= self.clipping_fraction <= 1.0:
            raise ValueError("clipping fraction outside [0, 1]")


@dataclass(frozen=True)
class OriginTrace:
    episode_seed: int
    mode: int
    step: int
    event_locations_evaluator_only: tuple[int, ...]
    rollout_horizons: dict[int, tuple[RolloutStep, ...]]
    one_step_innovation_score: float
    one_step_authority: float
    one_step_null_error_evaluator_only: float
    one_step_learned_error_evaluator_only: float
    one_step_gated_error_evaluator_only: float

    def validate(self) -> None:
        if set(self.rollout_horizons) != {1, 8, 32}:
            raise ValueError("trace must contain H1, H8, and H32 rollouts")
        for horizon, rows in self.rollout_horizons.items():
            if len(rows) != horizon:
                raise ValueError(f"H{horizon} rollout has wrong length")
            for offset, row in enumerate(rows):
                row.validate()
                if row.offset != offset:
                    raise ValueError("rollout offsets are not contiguous")
        _finite(
            (
                self.one_step_innovation_score,
                self.one_step_authority,
                self.one_step_null_error_evaluator_only,
                self.one_step_learned_error_evaluator_only,
                self.one_step_gated_error_evaluator_only,
            ),
            "origin trace",
        )


def rollout_step_to_dict(row: RolloutStep) -> dict[str, object]:
    row.validate()
    payload = {
        "offset": row.offset,
        "null_prediction": list(row.null_prediction),
        "learned_only_prediction": list(row.learned_only_prediction),
        "gated_prediction": list(row.gated_prediction),
        "target_evaluator_only": list(row.target_evaluator_only),
        "innovation_score": row.innovation_score,
        "authority": row.authority,
        NULL_LOCAL_ERROR_FIELD: row.null_local_error_evaluator_only,
        LEARNED_ONLY_LOCAL_ERROR_FIELD: row.learned_only_local_error_evaluator_only,
        GATED_LOCAL_ERROR_FIELD: row.gated_local_error_evaluator_only,
        "clipping_fraction": row.clipping_fraction,
    }
    validate_rollout_step_payload(payload)
    return payload


def validate_rollout_step_payload(payload: Mapping[str, object]) -> None:
    """Enforce the serialized rollout-step field contract fail-closed."""

    fields = set(payload)
    if LEGACY_LEARNED_LOCAL_ERROR_FIELD in fields:
        raise ValueError(
            "rollout step uses deprecated learned error field; expected "
            f"{LEARNED_ONLY_LOCAL_ERROR_FIELD}"
        )

    missing = ROLLOUT_STEP_FIELDS - fields
    if missing:
        raise ValueError(
            "rollout step is missing required fields: "
            + ", ".join(sorted(missing))
        )

    unexpected = fields - ROLLOUT_STEP_FIELDS
    if unexpected:
        raise ValueError(
            "rollout step contains unknown fields: "
            + ", ".join(sorted(unexpected))
        )


def origin_trace_to_dict(row: OriginTrace) -> dict[str, object]:
    row.validate()
    return {
        "episode_seed_evaluator_only": row.episode_seed,
        "mode_evaluator_only": row.mode,
        "step": row.step,
        "event_locations_evaluator_only": list(row.event_locations_evaluator_only),
        "rollout_horizons": {
            str(horizon): [rollout_step_to_dict(item) for item in rows]
            for horizon, rows in sorted(row.rollout_horizons.items())
        },
        "one_step_innovation_score": row.one_step_innovation_score,
        "one_step_authority": row.one_step_authority,
        "one_step_null_error_evaluator_only": row.one_step_null_error_evaluator_only,
        "one_step_learned_error_evaluator_only": row.one_step_learned_error_evaluator_only,
        "one_step_gated_error_evaluator_only": row.one_step_gated_error_evaluator_only,
    }
