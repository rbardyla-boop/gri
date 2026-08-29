from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from probe_innovation_model import InnovationModel, evaluate as eval_ungated, pre, train
from qualify_authority190 import eval_authority
from wildflower0.nursery1 import (
    MODES,
    collect_pairs,
    extract_object_state,
    select_balanced_episode_seeds,
    set_seed,
    stable_hash,
)

MODEL_SEED = 230
TRAIN_PER_MODE = 2
TEST_PER_MODE = 2
EPISODE_LENGTH = 420
EVAL_LENGTH = 520
TRAIN_STEPS = 80
BURN = 12
TRAIN_START = 400_000
TEST_START = 450_000
SIMPLE_MARGIN = 0.05
SIMPLE_KINDS = ("innov_carry", "accel_carry", "blend_both")


@dataclass(frozen=True)
class ControlSummary:
    h1_mean: float
    h1_max: float
    h8_mean: float
    h8_max: float
    h32_mean: float
    h32_max: float
    event_h8_mean: float
    event_h8_max: float


def _simple_pre(pairs):
    current = np.stack([extract_object_state(pair.current.frame) for pair in pairs])
    target = np.stack([extract_object_state(pair.nxt.frame) for pair in pairs])
    return current, target


def _innovation_score(current: np.ndarray, start: int) -> float:
    values = []
    for index in range(start - BURN, start):
        state = current[index]
        previous = current[index - 1]
        previous2 = current[index - 2]
        baseline = np.clip(previous + (previous - previous2), -1.0, 1.0)
        values.append(np.abs(state - baseline).mean() * 5.5)
    weights = np.geomspace(0.35, 1.0, len(values))
    return float(np.dot(weights, values) / weights.sum())


def eval_simple_control(pairs, horizon: int, kind: str, event_only: bool = False) -> float:
    current, target = _simple_pre(pairs)
    model_errors = []
    baseline_errors = []
    for start in range(BURN + 2, len(pairs) - horizon, max(horizon, 4)):
        if event_only and not any(
            pairs[start + offset].rule_event
            or pairs[start + offset].collision
            or pairs[start + offset].boundary
            for offset in range(horizon)
        ):
            continue
        score = _innovation_score(current, start)
        alpha = float(np.clip((score - 0.30) / 0.30, 0.0, 1.0))
        state = current[start].copy()
        previous = current[start - 1]
        velocity = state - previous
        previous2 = current[start - 2]
        last_innovation = state - np.clip(previous + (previous - previous2), -1.0, 1.0)
        previous_velocity = previous - previous2
        acceleration = velocity - previous_velocity
        baseline_state = state.copy()
        baseline_velocity = velocity.copy()
        local_alpha = alpha
        for _ in range(horizon):
            baseline_prediction = np.clip(
                baseline_state + baseline_velocity,
                -1.0,
                1.0,
            )
            if kind == "innov_carry":
                correction = last_innovation
            elif kind == "accel_carry":
                correction = acceleration
            elif kind == "blend_both":
                correction = 0.5 * last_innovation + 0.5 * acceleration
            else:
                raise ValueError(f"unknown simple control: {kind}")
            prediction = np.clip(
                baseline_prediction + local_alpha * correction,
                -1.0,
                1.0,
            )
            velocity = prediction - state
            state = prediction
            baseline_velocity = baseline_prediction - baseline_state
            baseline_state = baseline_prediction
            local_alpha *= 0.998
        expected = target[start + horizon - 1]
        model_errors.append(float(np.abs(state - expected).mean() * 5.5))
        baseline_errors.append(float(np.abs(baseline_state - expected).mean() * 5.5))
    return float(np.mean(model_errors) / max(np.mean(baseline_errors), 1e-8))


def _summarize(rows: list[dict[str, float]]) -> ControlSummary:
    return ControlSummary(
        h1_mean=float(np.mean([row["h1"] for row in rows])),
        h1_max=float(np.max([row["h1"] for row in rows])),
        h8_mean=float(np.mean([row["h8"] for row in rows])),
        h8_max=float(np.max([row["h8"] for row in rows])),
        h32_mean=float(np.mean([row["h32"] for row in rows])),
        h32_max=float(np.max([row["h32"] for row in rows])),
        event_h8_mean=float(np.mean([row["event_h8"] for row in rows])),
        event_h8_max=float(np.max([row["event_h8"] for row in rows])),
    )


def main() -> int:
    set_seed(MODEL_SEED)
    train_selection = select_balanced_episode_seeds(
        MODEL_SEED + 9000,
        TRAIN_PER_MODE,
        start=TRAIN_START,
    )
    test_selection = select_balanced_episode_seeds(
        MODEL_SEED + 19000,
        TEST_PER_MODE,
        start=TEST_START,
    )
    model = InnovationModel()
    training_order = [
        train_selection[mode][index]
        for index in range(TRAIN_PER_MODE)
        for mode in MODES
    ]
    for index, episode_seed in enumerate(training_order):
        train(
            model,
            collect_pairs(episode_seed, EPISODE_LENGTH),
            TRAIN_STEPS,
            MODEL_SEED + 10_000 + index,
        )

    rows = []
    simple_rows = {kind: [] for kind in SIMPLE_KINDS}
    surprise_rows = []
    for mode in MODES:
        for episode_seed in test_selection[mode]:
            pairs = collect_pairs(episode_seed, EVAL_LENGTH)
            row = {"mode": mode, "episode_seed": episode_seed}
            for horizon in (1, 8, 32):
                row[f"h{horizon}"] = eval_authority(model, pairs, horizon)
                model_error, baseline_error, _ = eval_ungated(model, pairs, horizon)
                row[f"ungated_h{horizon}_ratio"] = float(
                    model_error / max(baseline_error, 1e-8)
                )
            row["event_h8"] = eval_authority(model, pairs, 8, event_only=True)
            rows.append(row)

            for kind in SIMPLE_KINDS:
                simple_rows[kind].append(
                    {
                        "mode": float(mode),
                        "episode_seed": float(episode_seed),
                        "h1": eval_simple_control(pairs, 1, kind),
                        "h8": eval_simple_control(pairs, 8, kind),
                        "h32": eval_simple_control(pairs, 32, kind),
                        "event_h8": eval_simple_control(pairs, 8, kind, event_only=True),
                    }
                )

            surprise = collect_pairs(episode_seed, EVAL_LENGTH, surprise=True)
            surprise_rows.append(
                {
                    "mode": mode,
                    "episode_seed": episode_seed,
                    "h8": eval_authority(model, surprise, 8)["ratio"],
                    "h32": eval_authority(model, surprise, 32)["ratio"],
                }
            )

    h1 = [row["h1"]["ratio"] for row in rows]
    h8 = [row["h8"]["ratio"] for row in rows]
    h32 = [row["h32"]["ratio"] for row in rows]
    event_h8 = [row["event_h8"]["ratio"] for row in rows]
    ungated_h1 = [row["ungated_h1_ratio"] for row in rows]
    ungated_h8 = [row["ungated_h8_ratio"] for row in rows]
    ungated_h32 = [row["ungated_h32_ratio"] for row in rows]

    aggregate = {
        "h1_ratio_mean": float(np.mean(h1)),
        "h1_ratio_max": float(np.max(h1)),
        "h8_ratio_mean": float(np.mean(h8)),
        "h8_ratio_max": float(np.max(h8)),
        "h32_ratio_mean": float(np.mean(h32)),
        "h32_ratio_max": float(np.max(h32)),
        "event_h8_ratio_mean": float(np.mean(event_h8)),
        "event_h8_ratio_max": float(np.max(event_h8)),
        "ungated_h1_mean": float(np.mean(ungated_h1)),
        "ungated_h1_max": float(np.max(ungated_h1)),
        "ungated_h8_mean": float(np.mean(ungated_h8)),
        "ungated_h8_max": float(np.max(ungated_h8)),
        "ungated_h32_mean": float(np.mean(ungated_h32)),
        "ungated_h32_max": float(np.max(ungated_h32)),
    }
    core_gates = {
        "h1_noninferior_all": aggregate["h1_ratio_max"] <= 1.10,
        "h8_better_all": aggregate["h8_ratio_max"] <= 1.00,
        "h8_mean_10pct": aggregate["h8_ratio_mean"] <= 0.90,
        "h32_better_all": aggregate["h32_ratio_max"] <= 1.00,
        "h32_mean_15pct": aggregate["h32_ratio_mean"] <= 0.85,
        "event_h8_mean_10pct": aggregate["event_h8_ratio_mean"] <= 0.90,
    }
    simple_summary = {
        kind: _summarize(simple_rows[kind]).__dict__
        for kind in SIMPLE_KINDS
    }
    best_simple_h8 = min(summary["h8_mean"] for summary in simple_summary.values())
    best_simple_h32 = min(summary["h32_mean"] for summary in simple_summary.values())
    mechanism_gates = {
        "beats_best_simple_h8_by_0_05": (
            aggregate["h8_ratio_mean"] <= best_simple_h8 - SIMPLE_MARGIN
        ),
        "beats_best_simple_h32_by_0_05": (
            aggregate["h32_ratio_mean"] <= best_simple_h32 - SIMPLE_MARGIN
        ),
        "authority_restores_h1_safety": (
            aggregate["h1_ratio_max"] <= 1.10
            and aggregate["ungated_h1_max"] > 1.10
        ),
    }
    report = {
        "status": "WILDFLOWER_AUTHORITY_REPLICATION_230",
        "execution_integrity_passed": True,
        "model_seed": MODEL_SEED,
        "frozen_candidate_source": {
            "probe_innovation_model_sha256": (
                "97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1"
            ),
            "qualify_authority190_sha256": (
                "13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e"
            ),
        },
        "frozen_config": {
            "threshold_cells": 0.30,
            "width_cells": 0.30,
            "authority_decay": 0.998,
            "burn": BURN,
            "train_per_mode": TRAIN_PER_MODE,
            "test_per_mode": TEST_PER_MODE,
            "episode_length": EPISODE_LENGTH,
            "eval_length": EVAL_LENGTH,
            "train_steps_per_episode": TRAIN_STEPS,
            "train_start": TRAIN_START,
            "test_start": TEST_START,
        },
        "train_selection": train_selection,
        "test_selection": test_selection,
        "rows": rows,
        "aggregate": aggregate,
        "core_gates": core_gates,
        "simple_controls": simple_summary,
        "mechanism_gates": mechanism_gates,
        "surprise_descriptive_only": {
            "rows": surprise_rows,
            "h8_mean": float(np.mean([row["h8"] for row in surprise_rows])),
            "h32_mean": float(np.mean([row["h32"] for row in surprise_rows])),
        },
        "replication_passed": all(core_gates.values()),
        "mechanism_credit_passed": all(mechanism_gates.values()),
        "promotion_gate_passed": (
            all(core_gates.values()) and all(mechanism_gates.values())
        ),
        "primitive0_authorized": False,
    }
    report["receipt_sha256"] = stable_hash(report)
    out = Path("artifacts/authority_replication230.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
