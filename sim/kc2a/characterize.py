#!/usr/bin/env python3
"""KC-2A-D two-cell knowledge transfer characterization."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from sim.kc0.kc1a.cell import KC1ACell
from sim.kc0.validate_bank import load_bank, sha256, validate_bank
from sim.runtime import canonical, tensor_digest
from sim.kc2a.transfer import deliver_transfer, prepare_transfer, resource_manifest, source_contains

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
TRANSFER_PATH = HERE / "transfer.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_ids(bank: dict[str, Any]) -> dict[str, int]:
    return {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}


def fresh_cell_state() -> tuple[KC1ACell, torch.Tensor]:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    return cell, state


def write(cell: KC1ACell, state: torch.Tensor, tokens: list[int]) -> torch.Tensor:
    for token in tokens:
        state = cell.step(torch.tensor([token], dtype=torch.int64), state)
    return state


def contains_all(state: torch.Tensor, tokens: list[int]) -> bool:
    return all(source_contains(state, token) for token in tokens)


def state_digest(state: torch.Tensor) -> str:
    return tensor_digest(state)


def audit_transfer_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    classes = 0
    global_statements = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, ast.Global):
            global_statements += 1
    forbidden = sorted(names & {"packet_history", "history", "shadow", "cache", "global_memory", "population", "replication", "knowledge_store"})
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 else "FAIL",
        "forbidden_names": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
    }


def exact_transfer(ids: dict[str, int], packet: str) -> dict[str, Any]:
    source_cell, source_state = fresh_cell_state()
    target_cell, target_state = fresh_cell_state()
    token = ids[packet]
    source_state = write(source_cell, source_state, [token])
    payload = prepare_transfer(source_state, token)
    target_state = deliver_transfer(target_cell, target_state, payload)
    return {
        "packet": packet,
        "source_contains": source_contains(source_state, token),
        "target_contains": source_contains(target_state, token),
        "source_state_sha256": state_digest(source_state),
        "target_state_sha256": state_digest(target_state),
        "payload_sha256": hashlib.sha256(str(payload).encode("ascii")).hexdigest(),
        "separate_state": source_state.data_ptr() != target_state.data_ptr(),
    }


def build_characterization(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ids = packet_ids(bank)
    base = [ids[value] for value in config["base_packets"]]
    second = [ids[value] for value in config["second_bank_packets"]]
    transfer_token = ids[config["transfer_packets"][0]]
    collision_token = ids[config["transfer_packets"][1]]

    source_cell, source_state = fresh_cell_state()
    target_cell, target_state = fresh_cell_state()
    source_state = write(source_cell, source_state, [transfer_token])
    isolation = {
        "source_contains": source_contains(source_state, transfer_token),
        "target_empty": not source_contains(target_state, transfer_token),
        "separate_state": source_state.data_ptr() != target_state.data_ptr(),
    }

    transfer = exact_transfer(ids, config["transfer_packets"][0])

    duplicate_cell, duplicate_state = fresh_cell_state()
    dup_payload = prepare_transfer(source_state, transfer_token)
    duplicate_state = deliver_transfer(duplicate_cell, duplicate_state, dup_payload)
    first_digest = state_digest(duplicate_state)
    duplicate_state = deliver_transfer(duplicate_cell, duplicate_state, dup_payload)
    duplicate = {
        "first_state_sha256": first_digest,
        "second_state_sha256": state_digest(duplicate_state),
        "unchanged": first_digest == state_digest(duplicate_state),
        "contains": source_contains(duplicate_state, transfer_token),
    }

    collision_source, collision_source_state = fresh_cell_state()
    collision_target, collision_target_state = fresh_cell_state()
    collision_source_state = write(collision_source, collision_source_state, [collision_token])
    collision_target_state = write(collision_target, collision_target_state, [transfer_token])
    collision_payload = prepare_transfer(collision_source_state, collision_token)
    collision_target_state = deliver_transfer(collision_target, collision_target_state, collision_payload)
    collision = {
        "source_contains_new": source_contains(collision_source_state, collision_token),
        "target_contains_new": source_contains(collision_target_state, collision_token),
        "target_contains_old": source_contains(collision_target_state, transfer_token),
    }

    restart_source, restart_source_state = fresh_cell_state()
    restart_target, restart_target_state = fresh_cell_state()
    restart_source_state = write(restart_source, restart_source_state, [transfer_token])
    transient_payload = prepare_transfer(restart_source_state, transfer_token)
    source_payload = restart_source.serialize_state(restart_source_state)
    target_payload = restart_target.serialize_state(restart_target_state)
    restarted_source = KC1ACell().restore_state(source_payload, dtype=torch.int64, device=torch.device("cpu"))
    restarted_target = KC1ACell().restore_state(target_payload, dtype=torch.int64, device=torch.device("cpu"))
    restarted_target = deliver_transfer(KC1ACell(), restarted_target, transient_payload)
    restart_transfer = {
        "source_contains": source_contains(restarted_source, transfer_token),
        "target_contains": source_contains(restarted_target, transfer_token),
        "source_state_bytes": len(source_payload),
        "target_state_bytes": len(target_payload),
    }

    source_a, state_a = fresh_cell_state()
    source_b, state_b = fresh_cell_state()
    state_a = write(source_a, state_a, base)
    state_b = write(source_b, state_b, second)
    distributed = {
        "source_current": sum(source_contains(state_a, token) for token in base),
        "target_current": sum(source_contains(state_b, token) for token in second),
        "pair_current": sum(source_contains(state_a, token) for token in base) + sum(source_contains(state_b, token) for token in second),
        "source_occupied_slots": int(state_a[0, 8:].sum()),
        "target_occupied_slots": int(state_b[0, 8:].sum()),
    }

    loss_source, loss_state = fresh_cell_state()
    loss_target, loss_target_state = fresh_cell_state()
    loss_state = write(loss_source, loss_state, [transfer_token])
    loss_target_state = deliver_transfer(loss_target, loss_target_state, prepare_transfer(loss_state, transfer_token))
    del loss_source, loss_state
    source_loss = {"target_survives": source_contains(loss_target_state, transfer_token)}

    dest_source, dest_source_state = fresh_cell_state()
    dest_target, dest_target_state = fresh_cell_state()
    dest_source_state = write(dest_source, dest_source_state, [transfer_token])
    del dest_target, dest_target_state
    replacement_target, replacement_state = fresh_cell_state()
    replacement_state = deliver_transfer(replacement_target, replacement_state, prepare_transfer(dest_source_state, transfer_token))
    destination_loss = {
        "source_survives_before_transfer": source_contains(dest_source_state, transfer_token),
        "replacement_target_receives": source_contains(replacement_state, transfer_token),
    }

    return {
        "isolation": isolation,
        "explicit_transfer": transfer,
        "duplicate_delivery": duplicate,
        "collision_delivery": collision,
        "restart_during_transfer": restart_transfer,
        "distributed_capacity": distributed,
        "source_loss_survival": source_loss,
        "destination_loss_before_transfer": destination_loss,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    anchor_errors = []
    if sha256(CELL_PATH) != config.get("cell_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")
    resource = resource_manifest()
    transfer_audit = audit_transfer_source(TRANSFER_PATH)
    resource_pass = resource == {
        "coordinator_state_bytes": config["coordinator_state_bytes"],
        "coordinator_persistent_fields": config["coordinator_persistent_fields"],
        "transfer_payload_persistent": config["transfer_payload_persistent"],
        "uses_packet_history": False,
        "uses_shadow_slot_table": False,
        "uses_global_memory": False,
        "uses_population_logic": False,
        "uses_replication": False,
    }
    first = build_characterization(bank, config)
    second = build_characterization(bank, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "coordinator_state_zero": resource_pass,
        "transfer_source_audit": transfer_audit["status"] == "PASS",
        "isolation": first["isolation"]["source_contains"] and first["isolation"]["target_empty"] and first["isolation"]["separate_state"],
        "explicit_transfer": first["explicit_transfer"]["source_contains"] and first["explicit_transfer"]["target_contains"],
        "duplicate_delivery": first["duplicate_delivery"]["unchanged"],
        "collision_delivery": first["collision_delivery"]["target_contains_new"] and not first["collision_delivery"]["target_contains_old"],
        "restart_during_transfer": first["restart_during_transfer"]["source_contains"] and first["restart_during_transfer"]["target_contains"],
        "distributed_capacity": first["distributed_capacity"]["pair_current"] == 16,
        "source_loss_survival": first["source_loss_survival"]["target_survives"],
        "destination_loss_before_transfer": first["destination_loss_before_transfer"]["source_survives_before_transfer"] and first["destination_loss_before_transfer"]["replacement_target_receives"],
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-2A-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_2A_DEV_COMPLETE" if passed else "KC_2A_DEV_INVALID",
        "cell_candidate_id": config["cell_candidate_id"],
        "cell_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "transfer_source_sha256": sha256(TRANSFER_PATH),
        "anchor_errors": anchor_errors,
        "coordinator_resource": resource,
        "transfer_source_audit": transfer_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development two-cell transfer characterization only; replication, population, and scientific conclusions are forbidden.",
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
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
