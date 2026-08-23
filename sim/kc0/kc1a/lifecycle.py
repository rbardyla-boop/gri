#!/usr/bin/env python3
"""Run the KC-1A lifecycle gate against the KC-0 development bank."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import torch

HERE = Path(__file__).resolve().parent

try:  # Package execution.
    from .audit import audit_source, sha256
    from .cell import KC1ACell
    from ...runtime import canonical, replay_recurrent_trace, run_recurrent_trace
    from ..validate_bank import load_bank, validate_bank
except ImportError:  # pragma: no cover - direct CLI path.
    sys.path.insert(0, str(HERE.parents[2]))
    from sim.kc0.kc1a.audit import audit_source, sha256
    from sim.kc0.kc1a.cell import KC1ACell
    from sim.runtime import canonical, replay_recurrent_trace, run_recurrent_trace
    from sim.kc0.validate_bank import load_bank, validate_bank


BANK_PATH = HERE.parent / "trial_bank.json"
MANIFEST_PATH = HERE / "manifest.json"
SOURCE_PATH = HERE / "cell.py"


def _active_tokens(bank: dict[str, Any], sequence: dict[str, Any], packet_ids: dict[str, int]) -> tuple[list[int], list[int], dict[str, int]]:
    tokens: list[int] = []
    query_positions: list[int] = []
    supervisor_events: dict[str, int] = {}
    for event in sequence["events"]:
        kind = event["kind"]
        supervisor_events[kind] = supervisor_events.get(kind, 0) + 1
        if kind == "CONSUME":
            tokens.append(packet_ids[event["packet_id"]])
        elif kind == "QUERY" and tokens:
            query_positions.append(len(tokens) - 1)
    return tokens, query_positions, supervisor_events


def run_lifecycle(bank_path: Path = BANK_PATH, manifest_path: Path = MANIFEST_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    packet_ids = {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}
    source_audit = audit_source(SOURCE_PATH, manifest_path)

    cell = KC1ACell()
    cold_a = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    cold_b = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    cold_start_pass = torch.equal(cold_a, cold_b)

    sequences = {sequence["sequence_id"]: sequence for sequence in bank["sequences"]}
    first_runs: list[dict[str, Any]] = []
    second_runs: list[dict[str, Any]] = []
    for trial in bank["trial_cards"]:
        for sequence_id in trial["fixture_sequences"]:
            sequence = sequences[sequence_id]
            tokens, query_positions, supervisor_events = _active_tokens(bank, sequence, packet_ids)
            trace = run_recurrent_trace(KC1ACell, tokens, query_positions)
            first_runs.append({"sequence_id": sequence_id, "split": sequence["split"], "supervisor_events": supervisor_events, "trace": trace})
            replay = replay_recurrent_trace(KC1ACell, tokens, query_positions)
            second_runs.append({"sequence_id": sequence_id, "split": sequence["split"], "supervisor_events": supervisor_events, "trace": replay["first"]})

    deterministic_pass = canonical(first_runs) == canonical(second_runs)
    restart_pass = all(item["trace"]["status"] == "PASS" for item in first_runs)
    mount_pass = len(first_runs) == len(bank["sequences"])
    checks = {
        "cold_start": cold_start_pass,
        "determinism": deterministic_pass,
        "restart": restart_pass,
        "containment": source_audit["status"] == "PASS",
        "accounting": source_audit["status"] == "PASS",
        "kc0_mount": mount_pass and bank_validation["status"] == "PASS",
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    receipt = {
        "unit": "KC-1A-LIFECYCLE",
        "status": status,
        "verdict": "KC_1A_LIFECYCLE_PASS" if status == "PASS" else "KC_1A_LIFECYCLE_FAIL",
        "candidate_id": "KC-1A-ISOLATED-KNOWLEDGE-CELL",
        "candidate_source_sha256": sha256(SOURCE_PATH),
        "candidate_manifest_sha256": sha256(manifest_path),
        "fixture_bank_sha256": sha256(bank_path),
        "scientific_execution": "FORBIDDEN",
        "scientific_verdicts": ["ADVANTAGE", "NO_ADVANTAGE", "LEARNED", "GENERALIZED", "REPLICATED"],
        "checks": checks,
        "source_audit": source_audit,
        "bank_validation": bank_validation,
        "sequence_count": len(first_runs),
        "sequence_trace_sha256": hashlib.sha256(canonical(first_runs).encode("utf-8")).hexdigest(),
        "note": "Lifecycle qualification only; no retention, superiority, learning, replication, or population claim is evaluated.",
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=BANK_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = run_lifecycle(args.bank, args.manifest, args.receipt)
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"], "sequence_count": receipt["sequence_count"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
