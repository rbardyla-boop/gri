from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from experiments.erc1.compiler import canonical_json
from experiments.erc2ar.contract import EVENTS_PUBLIC, EXPECTED_CASES, EXPECTED_PER_ACTUATOR, opaque_id

TRUTH_BY_ITEM = {
    1: "A1", 2: "A1", 4: "A1", 5: "A1", 6: "A1", 7: "A1",
    8: "A2", 9: "A2", 10: "A2", 11: "A2", 13: "A2",
    14: "A3", 19: "A3",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prediction_map(body: dict, ranking_key: str) -> dict[str, list[str]]:
    result = {}
    for row in body["predictions"]:
        oid = row["opaque_id"]
        if oid in result:
            raise ValueError(f"duplicate prediction {oid}")
        result[oid] = list(row[ranking_key])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    live = load(args.live)
    replay = load(args.replay)
    baseline = load(args.baseline)
    manifest = load(args.manifest)
    if manifest["case_count"] != EXPECTED_CASES:
        raise ValueError("manifest case count mismatch")
    if manifest["truth_labels_in_candidate_metadata"] or manifest["target_actuator_in_candidate_metadata"]:
        raise ValueError("truth leaked into candidate metadata")
    if live["case_count"] != EXPECTED_CASES or replay["case_count"] != EXPECTED_CASES or baseline["case_count"] != EXPECTED_CASES:
        raise ValueError("prediction case count mismatch")
    if live["prediction_seal_sha256"] != replay["prediction_seal_sha256"]:
        raise ValueError("live/replay prediction seal mismatch")
    if canonical_json(live["predictions"]) != canonical_json(replay["predictions"]):
        raise ValueError("live/replay prediction content mismatch")

    erc = prediction_map(live, "root_cause_service_ranking")
    simple = prediction_map(baseline, "actuator_ranking")
    expected_ids = {opaque_id(event) for event in EVENTS_PUBLIC}
    if set(erc) != expected_ids or set(simple) != expected_ids:
        raise ValueError("prediction identity set mismatch")

    details = []
    erc_correct = 0
    baseline_correct = 0
    per_actuator_total = Counter()
    per_actuator_correct = Counter()
    for event in EVENTS_PUBLIC:
        truth = TRUTH_BY_ITEM[event["item"]]
        oid = opaque_id(event)
        erc_top1 = erc[oid][0] if erc[oid] else None
        baseline_top1 = simple[oid][0] if simple[oid] else None
        eok = erc_top1 == truth
        bok = baseline_top1 == truth
        erc_correct += int(eok)
        baseline_correct += int(bok)
        per_actuator_total[truth] += 1
        per_actuator_correct[truth] += int(eok)
        details.append({
            "item": event["item"],
            "opaque_id": oid,
            "date": event["date"],
            "start": event["start"],
            "truth_actuator": truth,
            "erc_top1": erc_top1,
            "erc_correct": eok,
            "baseline_top1": baseline_top1,
            "baseline_correct": bok,
        })

    expected_distribution = Counter(EXPECTED_PER_ACTUATOR)
    if Counter(dict(per_actuator_total)) != expected_distribution:
        raise ValueError(f"truth distribution mismatch: {dict(per_actuator_total)}")
    per_actuator_pass = all(per_actuator_correct[a] == EXPECTED_PER_ACTUATOR[a] for a in EXPECTED_PER_ACTUATOR)

    if erc_correct == EXPECTED_CASES and per_actuator_pass:
        if baseline_correct <= 11:
            status = "ERC2AR_STRICT_TRANSFER_PASS"
        else:
            status = "ERC2AR_TRANSFER_PASS_SIMPLE_RULE_SUFFICIENT"
    else:
        status = "ERC2AR_TRANSFER_DISCREPANCY"

    result = {
        "unit": "ERC-2AR",
        "status": status,
        "scientific_case_count": EXPECTED_CASES,
        "erc_top1_correct": erc_correct,
        "erc_top1_rate": erc_correct / EXPECTED_CASES,
        "baseline_top1_correct": baseline_correct,
        "baseline_top1_rate": baseline_correct / EXPECTED_CASES,
        "per_actuator_total": dict(sorted(per_actuator_total.items())),
        "per_actuator_erc_correct": dict(sorted(per_actuator_correct.items())),
        "per_actuator_pass": per_actuator_pass,
        "live_prediction_seal_sha256": live["prediction_seal_sha256"],
        "replay_prediction_seal_sha256": replay["prediction_seal_sha256"],
        "baseline_prediction_seal_sha256": baseline["prediction_seal_sha256"],
        "details": details,
        "same_set_rescue_authorized": False,
        "semantic_claim": False,
        "llm_calls": 0,
    }
    result["record_sha256"] = sha256_text(canonical_json(result))
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
