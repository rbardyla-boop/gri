from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def prediction_seal(predictions: Iterable[dict]) -> str:
    return hashlib.sha256(canonical_bytes(list(predictions))).hexdigest()


def verify_prediction_seals(live_predictions: list[dict], replay_predictions: list[dict]) -> str:
    live_bytes = canonical_bytes(live_predictions)
    replay_bytes = canonical_bytes(replay_predictions)
    if live_bytes != replay_bytes:
        raise ValueError("live/replay prediction serialization mismatch")
    return hashlib.sha256(live_bytes).hexdigest()


def _truth_by_opaque(scorer_map: list[dict]) -> dict[str, dict]:
    truth = {}
    for row in scorer_map:
        opaque_id = row.get("opaque_id")
        values = row.get("truth")
        if not isinstance(opaque_id, str) or not isinstance(values, dict):
            raise ValueError("invalid scorer map row")
        if opaque_id in truth:
            raise ValueError("duplicate scorer opaque id")
        if set(values) != {"fault_target", "sc_type"}:
            raise ValueError("scorer truth schema mismatch")
        truth[opaque_id] = values
    return truth


def _top1(prediction: dict, control: str) -> str:
    return prediction[control][0]["line_id"]


def score_after_prediction_seals(
    *,
    live_predictions: list[dict],
    replay_predictions: list[dict],
    scorer_map: list[dict],
) -> dict:
    """Scoring is callable only after byte-identical live/replay prediction seals."""

    seal = verify_prediction_seals(live_predictions, replay_predictions)
    truth = _truth_by_opaque(scorer_map)
    prediction_ids = [prediction["opaque_id"] for prediction in live_predictions]
    if len(set(prediction_ids)) != len(prediction_ids):
        raise ValueError("duplicate prediction opaque id")
    if set(truth) != set(prediction_ids):
        raise ValueError("scorer/prediction case set mismatch")

    counts = {"primary": 0, "single_ended": 0, "magnitude_only": 0}
    per_line = {line: 0 for line in ("Line_1_2_a", "Line_1_2_b", "Line_2_3_a", "Line_2_3_b")}
    truth_line_counts = Counter(row["fault_target"] for row in truth.values())
    for prediction in live_predictions:
        target = truth[prediction["opaque_id"]]["fault_target"]
        for control in counts:
            if _top1(prediction, control) == target:
                counts[control] += 1
        if _top1(prediction, "primary") == target:
            per_line[target] += 1

    primary_margin_over_magnitude = counts["primary"] - counts["magnitude_only"]
    primary_margin_over_single = counts["primary"] - counts["single_ended"]
    accuracy_gate = len(live_predictions) == 64 and counts["primary"] >= 60
    per_line_gate = (
        len(live_predictions) == 64
        and all(truth_line_counts[line] == 16 for line in per_line)
        and all(value >= 14 for value in per_line.values())
    )
    coordinated_gate = (
        accuracy_gate
        and per_line_gate
        and primary_margin_over_magnitude >= 8
        and primary_margin_over_single >= 4
    )
    simple_rule_gate = accuracy_gate and per_line_gate and not coordinated_gate
    interpretation = (
        "ERC3A_COORDINATED_ONSET_PASS"
        if coordinated_gate
        else "ERC3A_ONSET_SIGNAL_SIMPLE_RULE_SUFFICIENT"
        if simple_rule_gate
        else "ERC3A_TRANSFER_DISCREPANCY"
    )
    return {
        "status": "ERC3A_SCORED_AFTER_SEALS",
        "prediction_seal_sha256": seal,
        "case_count": len(live_predictions),
        "top1": counts,
        "primary_per_line": per_line,
        "primary_margin_over_magnitude": primary_margin_over_magnitude,
        "primary_margin_over_single_ended": primary_margin_over_single,
        "gates": {
            "primary_top1_at_least_60": accuracy_gate,
            "primary_each_line_at_least_14": per_line_gate,
            "primary_margin_over_magnitude_at_least_8": primary_margin_over_magnitude >= 8,
            "primary_margin_over_single_ended_at_least_4": primary_margin_over_single >= 4,
        },
        "interpretation": interpretation,
        "same_set_rescue_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--scorer-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score_after_prediction_seals(
        live_predictions=json.loads(args.live.read_text(encoding="utf-8")),
        replay_predictions=json.loads(args.replay.read_text(encoding="utf-8")),
        scorer_map=json.loads(args.scorer_map.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
