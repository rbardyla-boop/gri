"""Exact evaluator-side gates for Predictive Authority 0.1."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from . import design
from .trace import ERROR_FIELD_BY_PATH, validate_rollout_step_payload


def _terminal(origin: dict[str, object], horizon: int) -> dict[str, float]:
    terminal = origin["rollout_horizons"][str(horizon)][-1]
    validate_rollout_step_payload(terminal)
    return terminal


def _error(origin: dict[str, object], horizon: int, name: str) -> float:
    try:
        field = ERROR_FIELD_BY_PATH[name]
    except KeyError as exc:
        raise ValueError(f"unknown rollout path: {name}") from exc
    return float(_terminal(origin, horizon)[field])


def _episode_ratio(
    origins: Iterable[dict[str, object]], horizon: int, name: str
) -> float:
    rows = tuple(origins)
    null_total = sum(_error(origin, horizon, "null") for origin in rows)
    chosen_total = sum(_error(origin, horizon, name) for origin in rows)
    if not rows or null_total <= 0.0:
        raise ValueError("episode ratio has an empty or zero denominator")
    return chosen_total / null_total


def _event_origin(origin: dict[str, object]) -> bool:
    start = int(origin["step"])
    return any(
        start <= int(event) < start + 8
        for event in origin["event_locations_evaluator_only"]
    )


def classify_h8_origin(origin: dict[str, object]) -> str:
    """Classify model and policy quality using exact H8 comparisons."""

    model_good = _error(origin, 8, "learned_only") <= _error(origin, 8, "null")
    policy_good = _error(origin, 8, "gated") <= _error(origin, 8, "null")
    if model_good and policy_good:
        return "MODEL_GOOD_POLICY_GOOD"
    if model_good and not policy_good:
        return "MODEL_GOOD_POLICY_HARMFUL"
    if not model_good and policy_good:
        return "MODEL_BAD_POLICY_PROTECTED"
    return "MODEL_BAD_POLICY_HARMFUL"


def nontriviality(authorities: Iterable[float]) -> dict[str, object]:
    values = tuple(float(value) for value in authorities)
    if not values:
        return {
            "eligible_origins": 0,
            "fraction_authority_gt_0_10": None,
            "mean_h8_authority_all_origins": None,
            "passed": False,
        }
    fraction = sum(value > 0.10 for value in values) / len(values)
    mean = sum(values) / len(values)
    return {
        "eligible_origins": len(values),
        "fraction_authority_gt_0_10": fraction,
        "mean_h8_authority_all_origins": mean,
        "passed": (
            design.gate_passes("h8_nontrivial_fraction", fraction)
            and design.gate_passes("h8_nontrivial_mean", mean)
        ),
    }


def evaluate_gates(origins: Iterable[dict[str, object]]) -> dict[str, object]:
    """Evaluate all frozen gates; empty/zero populations fail closed."""

    rows = tuple(origins)
    by_episode: dict[object, list[dict[str, object]]] = defaultdict(list)
    for origin in rows:
        by_episode[origin["episode_seed_evaluator_only"]].append(origin)

    episode_ratios = {
        "h1": [_episode_ratio(group, 1, "gated") for group in by_episode.values()],
        "h8": [_episode_ratio(group, 8, "gated") for group in by_episode.values()],
        "h32": [_episode_ratio(group, 32, "gated") for group in by_episode.values()],
        "event_h8": [
            _episode_ratio(
                [origin for origin in group if _event_origin(origin)],
                8,
                "gated",
            )
            for group in by_episode.values()
            if any(_event_origin(origin) for origin in group)
        ],
    }
    h8_worse = [
        origin
        for origin in rows
        if _error(origin, 8, "learned_only") > _error(origin, 8, "null")
    ]
    h8_useful = [
        origin
        for origin in rows
        if _error(origin, 8, "learned_only") < _error(origin, 8, "null")
    ]
    worse_null = sum(_error(origin, 8, "null") for origin in h8_worse)
    worse_gated = sum(_error(origin, 8, "gated") for origin in h8_worse)
    useful_gain = sum(
        _error(origin, 8, "null") - _error(origin, 8, "learned_only")
        for origin in h8_useful
    )
    captured_gain = sum(
        _error(origin, 8, "null") - _error(origin, 8, "gated")
        for origin in h8_useful
    )
    all_null_h1 = sum(_error(origin, 1, "null") for origin in rows)
    all_gated_h1 = sum(_error(origin, 1, "gated") for origin in rows)
    all_null_h32 = sum(_error(origin, 32, "null") for origin in rows)
    all_gated_h32 = sum(_error(origin, 32, "gated") for origin in rows)
    authority_means = [
        sum(float(item["authority"]) for item in origin["rollout_horizons"]["8"])
        / 8.0
        for origin in rows
    ]
    nontrivial = nontriviality(authority_means)

    def subset_gate(
        count: int, denominator: float, value: float, gate_name: str
    ) -> bool:
        return (
            count >= design.MIN_SUBSET_ORIGINS
            and denominator > 0.0
            and design.gate_passes(gate_name, value)
        )

    gates = {
        "old_h1_max": bool(episode_ratios["h1"])
        and design.gate_passes("old_h1_max", max(episode_ratios["h1"])),
        "old_h8_max": bool(episode_ratios["h8"])
        and design.gate_passes("old_h8_max", max(episode_ratios["h8"])),
        "old_h8_mean": bool(episode_ratios["h8"])
        and design.gate_passes(
            "old_h8_mean", sum(episode_ratios["h8"]) / len(episode_ratios["h8"])
        ),
        "old_h32_max": bool(episode_ratios["h32"])
        and design.gate_passes("old_h32_max", max(episode_ratios["h32"])),
        "old_h32_mean": bool(episode_ratios["h32"])
        and design.gate_passes(
            "old_h32_mean",
            sum(episode_ratios["h32"]) / len(episode_ratios["h32"]),
        ),
        "old_event_h8_mean": bool(episode_ratios["event_h8"])
        and design.gate_passes(
            "old_event_h8_mean",
            sum(episode_ratios["event_h8"]) / len(episode_ratios["event_h8"]),
        ),
        "h8_worse_learned_protection": subset_gate(
            len(h8_worse),
            worse_null,
            worse_gated / max(worse_null, 1e-12),
            "h8_worse_learned_protection",
        ),
        "h8_useful_learner_capture": subset_gate(
            len(h8_useful),
            useful_gain,
            captured_gain / max(useful_gain, 1e-12),
            "h8_useful_learner_capture",
        ),
        "h1_global_regression": all_null_h1 > 0.0
        and design.gate_passes(
            "h1_global_regression", all_gated_h1 / all_null_h1
        ),
        "h32_global_noninferiority": all_null_h32 > 0.0
        and design.gate_passes(
            "h32_global_noninferiority", all_gated_h32 / all_null_h32
        ),
        "nontriviality": bool(nontrivial["passed"]),
    }
    return {
        "gates": gates,
        "passed": all(gates.values()),
        "old_episode_ratios": episode_ratios,
        "h8_worse_learned": {
            "origins": len(h8_worse),
            "null_error_sum": worse_null,
            "gated_error_sum": worse_gated,
            "gated_null_ratio": (
                worse_gated / worse_null if worse_null > 0.0 else None
            ),
        },
        "h8_useful_learner": {
            "origins": len(h8_useful),
            "available_gain_sum": useful_gain,
            "captured_gain_sum": captured_gain,
            "capture_fraction": (
                captured_gain / useful_gain if useful_gain > 0.0 else None
            ),
        },
        "h1_global_ratio": all_gated_h1 / all_null_h1 if all_null_h1 > 0.0 else None,
        "h32_global_ratio": all_gated_h32 / all_null_h32 if all_null_h32 > 0.0 else None,
        "nontriviality": nontrivial,
        "h8_origin_classifications": {
            label: sum(classify_h8_origin(origin) == label for origin in rows)
            for label in (
                "MODEL_GOOD_POLICY_GOOD",
                "MODEL_GOOD_POLICY_HARMFUL",
                "MODEL_BAD_POLICY_PROTECTED",
                "MODEL_BAD_POLICY_HARMFUL",
            )
        },
    }
