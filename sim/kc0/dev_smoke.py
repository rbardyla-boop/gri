#!/usr/bin/env python3
"""Run fixture-only KC-0 development smoke checks.

This adapter exercises bank loading, event references, canonical traces, and
replay.  It intentionally has no cell implementation and cannot emit a
scientific verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:  # Works both as ``python sim/kc0/dev_smoke.py`` and as a package import.
    from .validate_bank import load_bank, sha256, validate_bank
except ImportError:  # pragma: no cover - exercised by the direct CLI path.
    from validate_bank import load_bank, sha256, validate_bank


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def trace_trial(bank: dict[str, Any], trial: dict[str, Any]) -> dict[str, Any]:
    sequences = {sequence["sequence_id"]: sequence for sequence in bank["sequences"]}
    events = []
    for sequence_id in trial["fixture_sequences"]:
        sequence = sequences[sequence_id]
        events.append({
            "sequence_id": sequence_id,
            "split": sequence["split"],
            "events": sequence["events"],
        })
    trace = {
        "trial_id": trial["trial_id"],
        "fixture_sequences": events,
        "event_count": sum(len(item["events"]) for item in events),
        "consume_count": sum(sum(event["kind"] == "CONSUME" for event in item["events"]) for item in events),
        "query_count": sum(sum(event["kind"] == "QUERY" for event in item["events"]) for item in events),
        "share_count": sum(sum(event["kind"] == "SHARE" for event in item["events"]) for item in events),
        "divide_count": sum(sum(event["kind"] == "DIVIDE" for event in item["events"]) for item in events),
    }
    trace["trace_sha256"] = hashlib.sha256(canonical(trace).encode("utf-8")).hexdigest()
    return trace


def run(bank_path: Path, receipt_path: Path | None = None) -> dict[str, Any]:
    validation = validate_bank(bank_path)
    if validation["status"] != "PASS":
        raise SystemExit(json.dumps(validation, indent=2, sort_keys=True))
    bank = load_bank(bank_path)
    first = [trace_trial(bank, trial) for trial in bank["trial_cards"]]
    second = [trace_trial(bank, trial) for trial in bank["trial_cards"]]
    replay_pass = canonical(first) == canonical(second)
    receipt = {
        "unit": "KC-0-FIXTURE-DEV-SMOKE",
        "mode": "DEV_SMOKE",
        "bank_sha256": sha256(bank_path),
        "candidate_present": False,
        "scientific_execution": "FORBIDDEN",
        "scientific_verdict": "FORBIDDEN",
        "fixture_validation": validation,
        "trial_count": len(first),
        "trials": first,
        "replay": {
            "status": "PASS" if replay_pass else "FAIL",
            "matched": replay_pass,
            "first_trace_sha256": hashlib.sha256(canonical(first).encode("utf-8")).hexdigest(),
            "second_trace_sha256": hashlib.sha256(canonical(second).encode("utf-8")).hexdigest(),
        },
        "status": "PASS" if replay_pass else "FAIL",
        "note": "Fixture/event-path smoke only; no candidate behavior was executed.",
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=Path(__file__).with_name("trial_bank.json"))
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = run(args.bank, args.receipt)
    print(json.dumps({"status": receipt["status"], "mode": receipt["mode"], "trial_count": receipt["trial_count"], "scientific_verdict": receipt["scientific_verdict"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
