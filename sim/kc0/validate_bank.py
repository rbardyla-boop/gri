#!/usr/bin/env python3
"""Validate the KC-0 development trial bank.

The bank is deliberately not executable research.  It freezes packet/query
fixtures and trial acceptance language while refusing candidate code,
scientific authorization, and scientific verdicts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_BANK = ROOT / "trial_bank.json"
EXPECTED_TRIALS = [f"KC-0{letter}" for letter in "ABCDEFGHIJ"]
ALLOWED_EVENT_KINDS = {"CONSUME", "QUERY", "SHARE", "DIVIDE", "RESET"}
FORBIDDEN_TOP_LEVEL_KEYS = {
    "candidate_source_sha256",
    "scientific_verdict",
    "execution_receipt",
    "authorization_receipt",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bank(path: Path = DEFAULT_BANK) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_bank(path: Path = DEFAULT_BANK) -> dict[str, Any]:
    errors: list[str] = []
    try:
        bank = load_bank(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "errors": [f"bank: unreadable: {exc}"], "path": str(path)}

    if bank.get("schema") != "KC-0-TRIAL-BANK-1":
        _error(errors, "bank: schema mismatch")
    if bank.get("status") != "DEV_TRIAL_BANK_ONLY":
        _error(errors, "bank: status must be DEV_TRIAL_BANK_ONLY")
    if bank.get("candidate_present") is not False:
        _error(errors, "bank: candidate_present must be false")
    if bank.get("scientific_authorization") is not False:
        _error(errors, "bank: scientific_authorization must be false")
    if bank.get("scientific_execution") != "FORBIDDEN":
        _error(errors, "bank: scientific_execution must be FORBIDDEN")
    if FORBIDDEN_TOP_LEVEL_KEYS.intersection(bank):
        _error(errors, "bank: scientific result/authorization fields are forbidden")

    world = bank.get("world")
    if not isinstance(world, dict):
        _error(errors, "bank: world section missing")
    else:
        expected_world = {
            "state_slots_per_cell": 8,
            "max_cells": 8,
            "packet_budget": 256,
            "seed": 20260821,
            "external_io": False,
            "arbitrary_code_execution": False,
            "network_access": False,
        }
        for key, expected in expected_world.items():
            if world.get(key) != expected:
                _error(errors, f"world: {key} must equal {expected!r}")

    packets = bank.get("packets")
    packet_ids: set[str] = set()
    if not isinstance(packets, list) or not packets:
        _error(errors, "packets: non-empty list required")
        packets = []
    for index, packet in enumerate(packets):
        if not isinstance(packet, dict):
            _error(errors, f"packets[{index}]: object required")
            continue
        packet_id = packet.get("packet_id")
        if not isinstance(packet_id, str) or not packet_id:
            _error(errors, f"packets[{index}]: packet_id required")
        elif packet_id in packet_ids:
            _error(errors, f"packets: duplicate packet_id {packet_id}")
        else:
            packet_ids.add(packet_id)
        for key in ("domain", "subject", "relation", "object"):
            if not isinstance(packet.get(key), str) or not packet[key]:
                _error(errors, f"packets[{index}]: {key} required")

    queries = bank.get("queries")
    query_ids: set[str] = set()
    if not isinstance(queries, list) or not queries:
        _error(errors, "queries: non-empty list required")
        queries = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            _error(errors, f"queries[{index}]: object required")
            continue
        query_id = query.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            _error(errors, f"queries[{index}]: query_id required")
        elif query_id in query_ids:
            _error(errors, f"queries: duplicate query_id {query_id}")
        else:
            query_ids.add(query_id)
        if query.get("expected") not in {"entailed", "contradicted", "unknown"}:
            _error(errors, f"queries[{index}]: invalid expected outcome")

    sequences = bank.get("sequences")
    sequence_ids: set[str] = set()
    if not isinstance(sequences, list) or not sequences:
        _error(errors, "sequences: non-empty list required")
        sequences = []
    for index, sequence in enumerate(sequences):
        if not isinstance(sequence, dict):
            _error(errors, f"sequences[{index}]: object required")
            continue
        sequence_id = sequence.get("sequence_id")
        if not isinstance(sequence_id, str) or not sequence_id:
            _error(errors, f"sequences[{index}]: sequence_id required")
        elif sequence_id in sequence_ids:
            _error(errors, f"sequences: duplicate sequence_id {sequence_id}")
        else:
            sequence_ids.add(sequence_id)
        if sequence.get("split") not in {"fit", "held_out"}:
            _error(errors, f"sequences[{index}]: split must be fit or held_out")
        events = sequence.get("events")
        if not isinstance(events, list) or not events:
            _error(errors, f"sequences[{index}]: non-empty events required")
            continue
        for event_index, event in enumerate(events):
            if not isinstance(event, dict):
                _error(errors, f"sequences[{index}].events[{event_index}]: object required")
                continue
            kind = event.get("kind")
            if kind not in ALLOWED_EVENT_KINDS:
                _error(errors, f"sequences[{index}].events[{event_index}]: invalid event kind")
            if kind == "CONSUME" and event.get("packet_id") not in packet_ids:
                _error(errors, f"sequences[{index}].events[{event_index}]: unknown packet")
            if kind == "QUERY" and event.get("query_id") not in query_ids:
                _error(errors, f"sequences[{index}].events[{event_index}]: unknown query")

    trial_cards = bank.get("trial_cards")
    if not isinstance(trial_cards, list):
        _error(errors, "trial_cards: list required")
        trial_cards = []
    trial_ids: list[str] = []
    for index, trial in enumerate(trial_cards):
        if not isinstance(trial, dict):
            _error(errors, f"trial_cards[{index}]: object required")
            continue
        trial_id = trial.get("trial_id")
        trial_ids.append(trial_id)
        if trial.get("status") != "SPEC_ONLY":
            _error(errors, f"trial_cards[{index}]: status must be SPEC_ONLY")
        if trial.get("scientific_execution_authorized") is not False:
            _error(errors, f"trial_cards[{index}]: execution must be unauthorized")
        if not isinstance(trial.get("question"), str) or not trial["question"]:
            _error(errors, f"trial_cards[{index}]: question required")
        refs = trial.get("fixture_sequences")
        if not isinstance(refs, list) or not refs:
            _error(errors, f"trial_cards[{index}]: fixture_sequences required")
        else:
            for ref in refs:
                if ref not in sequence_ids:
                    _error(errors, f"trial_cards[{index}]: unknown sequence {ref}")
        if not isinstance(trial.get("controls"), list) or not trial["controls"]:
            _error(errors, f"trial_cards[{index}]: controls required")
        if not isinstance(trial.get("metrics"), list) or not trial["metrics"]:
            _error(errors, f"trial_cards[{index}]: metrics required")
        acceptance = trial.get("acceptance")
        if not isinstance(acceptance, dict) or not acceptance.get("mode"):
            _error(errors, f"trial_cards[{index}]: machine-readable acceptance mode required")

    if trial_ids != EXPECTED_TRIALS:
        _error(errors, f"trial_cards: expected ordered ids {EXPECTED_TRIALS!r}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "bank_id": bank.get("bank_id"),
        "trial_ids": trial_ids,
        "packet_count": len(packet_ids),
        "query_count": len(query_ids),
        "sequence_count": len(sequence_ids),
        "sha256": sha256(path),
        "note": "Development fixtures only; no candidate or scientific verdict is present.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    args = parser.parse_args()
    result = validate_bank(args.bank)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

