#!/usr/bin/env python3
"""KC-1B-D single-cell retention characterization.

This is a development diagnostic around the frozen KC-1A source.  It records
matched traces and restart evidence but deliberately does not assign a
retention threshold or scientific verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import torch

HERE = Path(__file__).resolve().parent
KC0 = HERE.parent
ROOT = KC0.parent.parent
CELL_PATH = KC0 / "kc1a" / "cell.py"
BANK_PATH = KC0 / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"

try:  # Package execution.
    from ..kc1a.cell import KC1ACell
    from ..validate_bank import load_bank, sha256, validate_bank
    from ...runtime import canonical, tensor_digest
except ImportError:  # pragma: no cover - direct CLI path.
    sys.path.insert(0, str(ROOT))
    from sim.kc0.kc1a.cell import KC1ACell
    from sim.kc0.validate_bank import load_bank, sha256, validate_bank
    from sim.runtime import canonical, tensor_digest


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cycle(values: list[int], count: int) -> list[int]:
    if not count:
        return []
    return [values[index % len(values)] for index in range(count)]


def _state_record(cell: KC1ACell, state: torch.Tensor, target_token: int) -> dict[str, Any]:
    state_cpu = state.detach().cpu().to(torch.int64)
    values = state_cpu[0, :8].tolist()
    occupancy = state_cpu[0, 8:].tolist()
    slot = target_token % 8
    expected = target_token % 65535 + 1
    full = bool(occupancy[slot] == 1 and values[slot] == expected)
    value_only = bool(values[slot] == expected)
    occupancy_only = bool(occupancy[slot] == 1)
    readout = cell.readout(state).detach().cpu().tolist()
    return {
        "state": state_cpu.tolist(),
        "readout": readout,
        "state_sha256": tensor_digest(state_cpu),
        "readout_sha256": tensor_digest(cell.readout(state)),
        "target_slot": slot,
        "target_value": expected,
        "decoders": {
            "full_state": full,
            "value_only": value_only,
            "occupancy_only": occupancy_only,
        },
    }


def _l1(left: list[list[int]], right: list[list[int]]) -> int:
    return sum(abs(a - b) for a, b in zip(left[0], right[0]))


def run_tokens(tokens: list[int], target_token: int, split: int) -> dict[str, Any]:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    states = [state.detach().clone()]
    for token in tokens:
        state = cell.step(torch.tensor([token], dtype=torch.int64), state)
        states.append(state.detach().clone())
    uninterrupted = _state_record(cell, state, target_token)

    resumed_cell = KC1ACell()
    payload = cell.serialize_state(states[split])
    resumed = resumed_cell.restore_state(payload, dtype=torch.int64, device=torch.device("cpu"))
    for token in tokens[split:]:
        resumed = resumed_cell.step(torch.tensor([token], dtype=torch.int64), resumed)
    restarted = _state_record(resumed_cell, resumed, target_token)
    return {
        "tokens": tokens,
        "split": split,
        "serialization_bytes": len(payload),
        "serialization_sha256": hashlib.sha256(payload).hexdigest(),
        "uninterrupted": uninterrupted,
        "restarted": restarted,
        "restart_equal": uninterrupted["state"] == restarted["state"] and uninterrupted["readout"] == restarted["readout"],
    }


def build_characterization(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    packet_ids = {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}
    target_token = packet_ids[config["primary_packet"]]
    wrong_token = packet_ids[config["wrong_packet"]]
    standard = [packet_ids[value] for value in config["standard_distractors"]]
    altered = [packet_ids[value] for value in config["altered_distractors"]]
    rows: list[dict[str, Any]] = []

    for delay in config["delays"]:
        for distractor_name, distractors in (("standard", standard), ("altered", altered)):
            for condition in config["conditions"]:
                prefix = {"correct_packet": [target_token], "no_packet": [], "wrong_packet": [wrong_token]}[condition]
                prefix_length = len(prefix)
                tokens = prefix + _cycle(distractors, delay)
                split = min(len(tokens), prefix_length + delay // 2)
                run = run_tokens(tokens, target_token, split)
                rows.append({
                    "delay": delay,
                    "distractor_set": distractor_name,
                    "condition": condition,
                    "query_target": config["primary_packet"],
                    "result": run,
                })

    by_delay: list[dict[str, Any]] = []
    for delay in config["delays"]:
        standard_rows = [row for row in rows if row["delay"] == delay and row["distractor_set"] == "standard"]
        states = {row["condition"]: row["result"]["uninterrupted"]["state"] for row in standard_rows}
        correct = next(row for row in standard_rows if row["condition"] == "correct_packet")
        no_packet = next(row for row in standard_rows if row["condition"] == "no_packet")
        wrong = next(row for row in standard_rows if row["condition"] == "wrong_packet")
        by_delay.append({
            "delay": delay,
            "state_differentiation_l1": {
                "correct_vs_no": _l1(states["correct_packet"], states["no_packet"]),
                "correct_vs_wrong": _l1(states["correct_packet"], states["wrong_packet"]),
                "wrong_vs_no": _l1(states["wrong_packet"], states["no_packet"]),
            },
            "query_recoverability": {
                condition: correct["result"]["uninterrupted"]["decoders"][mode]
                for condition, correct in ((row["condition"], row) for row in standard_rows)
                for mode in ["full_state"]
            },
            "specificity": {
                "full_state_correct_minus_no": int(correct["result"]["uninterrupted"]["decoders"]["full_state"]) - int(no_packet["result"]["uninterrupted"]["decoders"]["full_state"]),
                "full_state_correct_minus_wrong": int(correct["result"]["uninterrupted"]["decoders"]["full_state"]) - int(wrong["result"]["uninterrupted"]["decoders"]["full_state"]),
            },
        })
    return {"rows": rows, "delay_summary": by_delay}


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    anchor_errors = []
    if sha256(CELL_PATH) != config.get("candidate_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    first = build_characterization(bank, config)
    second = build_characterization(bank, config)
    replay_pass = canonical(first) == canonical(second)
    restart_pass = all(row["result"]["restart_equal"] for row in first["rows"])
    harness_pass = not anchor_errors and bank_validation["status"] == "PASS" and replay_pass and restart_pass
    receipt = {
        "unit": "KC-1B-D",
        "status": "PASS" if harness_pass else "INVALID",
        "verdict": "KC_1B_DEV_COMPLETE" if harness_pass else "KC_1B_DEV_INVALID",
        "candidate_id": config["candidate_id"],
        "candidate_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "anchor_errors": anchor_errors,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "delays": config["delays"],
        "controls": config["conditions"],
        "readout_ablations": config["readout_ablations"],
        "metrics": config["metrics"],
        "restart_pass": restart_pass,
        "replay_pass": replay_pass,
        "row_count": len(first["rows"]),
        "delay_summary": first["delay_summary"],
        "characterization": first["rows"],
        "note": "Development characterization only; no retention threshold or scientific claim is assigned.",
    }
    receipt["canonical_receipt_sha256"] = hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=BANK_PATH)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = characterize(args.bank, args.config, args.receipt)
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"], "row_count": receipt["row_count"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
