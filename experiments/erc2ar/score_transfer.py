from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

EXPECTED_IDS = [f"E1-X{i:02d}" for i in range(1, 14)]
EXPECTED_TARGET_COUNTS = {"A1": 6, "A2": 5, "A3": 2}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", type=Path, required=True)
    p.add_argument("--replay", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--scorer-map", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    if args.live.read_bytes() != args.replay.read_bytes():
        raise ValueError("live/replay prediction bytes differ")
    live, replay, baseline, scorer, manifest = map(load, [args.live, args.replay, args.baseline, args.scorer_map, args.manifest])
    if live.get("case_count") != 13 or replay.get("case_count") != 13 or baseline.get("case_count") != 13:
        raise ValueError("case-count mismatch")
    if live.get("prediction_seal_sha256") != replay.get("prediction_seal_sha256"):
        raise ValueError("prediction seal mismatch")

    truth_rows = scorer.get("events", [])
    if sorted(r["opaque_id"] for r in truth_rows) != EXPECTED_IDS:
        raise ValueError("scorer ID set mismatch")
    truth = {r["opaque_id"]: r["true_actuator"] for r in truth_rows}
    if Counter(truth.values()) != Counter(EXPECTED_TARGET_COUNTS):
        raise ValueError("target distribution mismatch")

    manifest_rows = {r["opaque_id"]: r for r in manifest.get("events", [])}
    if sorted(manifest_rows) != EXPECTED_IDS:
        raise ValueError("manifest ID set mismatch")

    live_rows = {r["opaque_id"]: r for r in live["predictions"]}
    base_rows = {r["opaque_id"]: r for r in baseline["predictions"]}
    if sorted(live_rows) != EXPECTED_IDS or sorted(base_rows) != EXPECTED_IDS:
        raise ValueError("prediction ID set mismatch")

    provenance_failures = []
    capacity_failures = []
    erc_correct = 0
    erc_top3 = 0
    baseline_correct = 0
    per_actuator = defaultdict(lambda: {"n": 0, "erc_correct": 0, "baseline_correct": 0})
    disagreements = []

    for oid in EXPECTED_IDS:
        target = truth[oid]
        row = live_rows[oid]
        ranking = row.get("root_cause_service_ranking", [])
        if len(ranking) < 1:
            raise ValueError(f"empty ERC ranking {oid}")
        erc_hit = ranking[0] == target
        top3_hit = target in ranking[:3]
        base_rank = base_rows[oid].get("ranking", [])
        if len(base_rank) < 1:
            raise ValueError(f"empty baseline ranking {oid}")
        base_hit = base_rank[0] == target
        erc_correct += int(erc_hit)
        erc_top3 += int(top3_hit)
        baseline_correct += int(base_hit)
        per_actuator[target]["n"] += 1
        per_actuator[target]["erc_correct"] += int(erc_hit)
        per_actuator[target]["baseline_correct"] += int(base_hit)
        if not erc_hit or not base_hit or ranking[0] != base_rank[0]:
            disagreements.append({
                "opaque_id": oid,
                "target": target,
                "erc_top1": ranking[0],
                "erc_ranking": ranking,
                "baseline_top1": base_rank[0],
                "baseline_ranking": base_rank,
            })

        if int(row.get("packet_count", 999)) > 16:
            capacity_failures.append(oid)
        m = manifest_rows[oid]
        for packet_row in row.get("packet", []):
            if packet_row.get("opaque_id") != oid or packet_row.get("source_metrics_sha256") != m["source_metrics_sha256"] or packet_row.get("staged_metrics_sha256") != m["staged_metrics_sha256"]:
                provenance_failures.append({"opaque_id": oid, "evidence_id": packet_row.get("evidence_id")})

    per_actuator_plain = {k: dict(v) for k, v in sorted(per_actuator.items())}
    integrity = not provenance_failures and not capacity_failures and all(per_actuator_plain[a]["n"] == n for a, n in EXPECTED_TARGET_COUNTS.items())
    exact_per_actuator = all(per_actuator_plain[a]["erc_correct"] == n for a, n in EXPECTED_TARGET_COUNTS.items())

    if not integrity:
        status = "ERC2AR_INTEGRITY_INVALID"
    elif erc_correct < 13:
        status = "ERC2AR_TRANSFER_DISCREPANCY"
    elif erc_top3 != 13 or not exact_per_actuator:
        status = "ERC2AR_INTEGRITY_INVALID"
    elif baseline_correct <= 11:
        status = "ERC2AR_STRICT_TRANSFER_PASS"
    else:
        status = "ERC2AR_TRANSFER_PASS_SIMPLE_RULE_SUFFICIENT"

    report = {
        "unit": "ERC-2AR",
        "status": status,
        "scientific_n": 13,
        "erc_top1": {"correct": erc_correct, "n": 13, "rate": erc_correct / 13},
        "erc_top3": {"correct": erc_top3, "n": 13, "rate": erc_top3 / 13},
        "largest_single_shift_top1": {"correct": baseline_correct, "n": 13, "rate": baseline_correct / 13},
        "per_actuator": per_actuator_plain,
        "provenance_failures": provenance_failures,
        "capacity_failures": capacity_failures,
        "disagreements": disagreements,
        "live_prediction_sha256": sha256_file(args.live),
        "replay_prediction_sha256": sha256_file(args.replay),
        "prediction_seal_sha256": live["prediction_seal_sha256"],
        "baseline_prediction_seal_sha256": baseline["prediction_seal_sha256"],
        "scorer_map_sha256": sha256_file(args.scorer_map),
        "manifest_sha256": sha256_file(args.manifest),
        "live_replay_byte_identical": True,
        "compiler_model_calls": 0,
        "interpretation_boundary": "narrow DAMADICS physical-actuator structural transfer only",
    }
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
