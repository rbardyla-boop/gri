#!/usr/bin/env python3
"""KC-1D-D multi-item capacity and saturation characterization."""
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


def _packet_ids(bank: dict[str, Any]) -> dict[str, int]:
    return {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}


def _state_record(state: torch.Tensor, observed_tokens: list[int]) -> dict[str, Any]:
    value = state.detach().cpu().to(torch.int64)
    slots = value[0, :8].tolist()
    occupancy = value[0, 8:].tolist()
    observed = list(dict.fromkeys(observed_tokens))
    recoverable = [token for token in observed if slots[token % 8] == token % 65535 + 1 and occupancy[token % 8] == 1]
    return {
        "state": value.tolist(),
        "state_sha256": tensor_digest(value),
        "occupied_slots": int(sum(occupancy)),
        "observed_unique_packets": len(observed),
        "recoverable_current_values": len(recoverable),
        "recoverable_packet_tokens": recoverable,
        "recoverable_historical_values": len(recoverable),
    }


def run_tokens(tokens: list[int]) -> dict[str, Any]:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    states = [state.detach().clone()]
    seen_slots: set[int] = set()
    collisions = 0
    for token in tokens:
        slot = token % 8
        if slot in seen_slots:
            collisions += 1
        seen_slots.add(slot)
        state = cell.step(torch.tensor([token], dtype=torch.int64), state)
        states.append(state.detach().clone())
    uninterrupted = _state_record(state, tokens)
    restart_cell = KC1ACell()
    payload = cell.serialize_state(states[-1])
    restored = restart_cell.restore_state(payload, dtype=torch.int64, device=torch.device("cpu"))
    restarted = _state_record(restored, tokens)
    return {
        "tokens": tokens,
        "collision_write_count": collisions,
        "serialization_bytes": len(payload),
        "serialization_sha256": hashlib.sha256(payload).hexdigest(),
        "uninterrupted": uninterrupted,
        "restarted": restarted,
        "restart_equal": uninterrupted["state"] == restarted["state"],
    }


def build_characterization(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ids = _packet_ids(bank)
    base = [ids[value] for value in config["stored_packets_by_slot"].values()]
    collisions = [ids[value] for value in config["collision_packets"]]
    loads = []
    for size in config["load_sizes"]:
        tokens = base[: min(size, 8)]
        if size > 8:
            tokens += collisions[: size - 8]
        loads.append({"load": size, "result": run_tokens(tokens)})

    under_orders = [{"variant": name, "result": run_tokens([ids[token] for token in tokens])} for name, tokens in config["under_capacity_order_variants"].items()]
    over_orders = [{"variant": name, "result": run_tokens([ids[token] for token in tokens])} for name, tokens in config["over_capacity_order_variants"].items()]
    recency = [{"variant": name, "result": run_tokens([ids[token] for token in tokens])} for name, tokens in config["recency_sequences"].items()]
    full_bank = run_tokens(base)
    return {
        "loads": loads,
        "under_capacity_order": under_orders,
        "over_capacity_order": over_orders,
        "recency": recency,
        "full_bank_restart": full_bank,
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
    all_runs = first["loads"] + first["under_capacity_order"] + first["over_capacity_order"] + first["recency"] + [{"result": first["full_bank_restart"]}]
    restart_pass = all(item["result"]["restart_equal"] for item in all_runs)
    load_sizes = [item["load"] for item in first["loads"]]
    load_size_pass = load_sizes == config["load_sizes"]
    harness_pass = not anchor_errors and bank_validation["status"] == "PASS" and replay_pass and restart_pass and load_size_pass
    receipt = {
        "unit": "KC-1D-D",
        "status": "PASS" if harness_pass else "INVALID",
        "verdict": "KC_1D_DEV_COMPLETE" if harness_pass else "KC_1D_DEV_INVALID",
        "candidate_id": config["candidate_id"],
        "candidate_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "anchor_errors": anchor_errors,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": {
            "anchors": not anchor_errors,
            "load_bank_complete": load_size_pass,
            "restart": restart_pass,
            "replay": replay_pass,
        },
        "characterization": first,
        "note": "Development capacity/saturation characterization only; no capacity threshold or scientific conclusion is assigned.",
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
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"], "load_count": len(receipt["characterization"]["loads"])}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

