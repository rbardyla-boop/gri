#!/usr/bin/env python3
"""KC-1C-D single-cell interference-topology characterization."""
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
    return [values[index % len(values)] for index in range(count)] if count else []


def _state_record(state: torch.Tensor, target_token: int) -> dict[str, Any]:
    value = state.detach().cpu().to(torch.int64)
    values = value[0, :8].tolist()
    occupancy = value[0, 8:].tolist()
    slot = target_token % 8
    expected = target_token % 65535 + 1
    return {
        "state": value.tolist(),
        "state_sha256": tensor_digest(value),
        "target_slot": slot,
        "target_value": expected,
        "target_value_present": bool(values[slot] == expected),
        "target_occupancy_present": bool(occupancy[slot] == 1),
        "target_full_present": bool(values[slot] == expected and occupancy[slot] == 1),
    }


def run_tokens(tokens: list[int], target_token: int, split: int) -> dict[str, Any]:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    states = [state.detach().clone()]
    for token in tokens:
        state = cell.step(torch.tensor([token], dtype=torch.int64), state)
        states.append(state.detach().clone())
    uninterrupted = _state_record(state, target_token)
    restart_cell = KC1ACell()
    payload = cell.serialize_state(states[split])
    resumed = restart_cell.restore_state(payload, dtype=torch.int64, device=torch.device("cpu"))
    for token in tokens[split:]:
        resumed = restart_cell.step(torch.tensor([token], dtype=torch.int64), resumed)
    restarted = _state_record(resumed, target_token)
    return {
        "tokens": tokens,
        "split": split,
        "serialization_bytes": len(payload),
        "serialization_sha256": hashlib.sha256(payload).hexdigest(),
        "uninterrupted": uninterrupted,
        "restarted": restarted,
        "restart_equal": uninterrupted["state"] == restarted["state"],
    }


def effect_for(stored_token: int, incoming_token: int) -> str:
    if stored_token % 8 != incoming_token % 8:
        return "preserves"
    if stored_token == incoming_token:
        return "preserves_same_value"
    return "overwrites"


def build_characterization(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    packet_ids = {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}
    target = packet_ids[config["target_packet"]]
    collision = packet_ids[config["collision_packet"]]
    noncolliding = [packet_ids[value] for value in config["noncolliding_distractors"]]
    scenario_rows: list[dict[str, Any]] = []

    baseline_tokens = [target] + _cycle(noncolliding, config["total_distractors"])
    scenario_rows.append({"scenario": "no_collision_baseline", "collision_positions": [], "tokens": baseline_tokens, "result": run_tokens(baseline_tokens, target, 1 + config["total_distractors"] // 2)})
    for position in config["single_collision_positions"]:
        distractors = _cycle(noncolliding, config["total_distractors"])
        distractors[position] = collision
        tokens = [target] + distractors
        scenario_rows.append({"scenario": "single_collision", "collision_positions": [position], "tokens": tokens, "result": run_tokens(tokens, target, 1 + config["total_distractors"] // 2)})
    for count, positions in config["collision_count_positions"].items():
        distractors = _cycle(noncolliding, config["total_distractors"])
        for position in positions:
            distractors[position] = collision
        tokens = [target] + distractors
        scenario_rows.append({"scenario": f"collision_count_{count}", "collision_positions": positions, "tokens": tokens, "result": run_tokens(tokens, target, 1 + config["total_distractors"] // 2)})

    reobserve_tokens = [target, collision] + _cycle(noncolliding, 14) + [target]
    scenario_rows.append({"scenario": "reobserve_after_collision", "collision_positions": [0], "tokens": reobserve_tokens, "result": run_tokens(reobserve_tokens, target, 1 + 15 // 2)})

    matrix_rows: list[dict[str, Any]] = []
    for slot_text, stored_packet in config["stored_packets_by_slot"].items():
        stored_token = packet_ids[stored_packet]
        for incoming_packet in config["matrix_incoming_packets"]:
            incoming_token = packet_ids[incoming_packet]
            result = run_tokens([stored_token, incoming_token], stored_token, 1)
            matrix_rows.append({
                "stored_slot": int(slot_text),
                "stored_packet": stored_packet,
                "incoming_packet": incoming_packet,
                "incoming_slot": incoming_token % 8,
                "effect": effect_for(stored_token, incoming_token),
                "result": result,
            })

    return {
        "sequence_length": config["total_distractors"] + 1,
        "scenario_rows": scenario_rows,
        "interference_matrix": matrix_rows,
    }


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
    restart_pass = all(row["result"]["restart_equal"] for row in first["scenario_rows"]) and all(row["result"]["restart_equal"] for row in first["interference_matrix"])
    matrix_complete = len(first["interference_matrix"]) == 8 * len(config["matrix_incoming_packets"])
    sequence_length_constant = all(len(row["tokens"]) == config["total_distractors"] + 1 for row in first["scenario_rows"])
    harness_pass = not anchor_errors and bank_validation["status"] == "PASS" and replay_pass and restart_pass and matrix_complete and sequence_length_constant
    receipt = {
        "unit": "KC-1C-D",
        "status": "PASS" if harness_pass else "INVALID",
        "verdict": "KC_1C_DEV_COMPLETE" if harness_pass else "KC_1C_DEV_INVALID",
        "candidate_id": config["candidate_id"],
        "candidate_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "anchor_errors": anchor_errors,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": {
            "anchors": not anchor_errors,
            "sequence_length_constant": sequence_length_constant,
            "matrix_complete": matrix_complete,
            "restart": restart_pass,
            "replay": replay_pass,
        },
        "scenario_count": len(first["scenario_rows"]),
        "matrix_row_count": len(first["interference_matrix"]),
        "characterization": first,
        "note": "Development interference characterization only; no threshold or scientific conclusion is assigned.",
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
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"], "scenario_count": receipt["scenario_count"], "matrix_row_count": receipt["matrix_row_count"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
