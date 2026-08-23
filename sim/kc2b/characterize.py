#!/usr/bin/env python3
"""KC-2B-D oracle-free state export characterization."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
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
from sim.kc2b.export import deliver_export, export_slot, resource_manifest

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
EXPORT_PATH = HERE / "export.py"
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


def state_digest(state: torch.Tensor) -> str:
    return tensor_digest(state)


def audit_export_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    classes = 0
    global_statements = 0
    export_parameters: list[str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, ast.Global):
            global_statements += 1
        elif isinstance(node, ast.FunctionDef) and node.name == "export_slot":
            export_parameters = [argument.arg for argument in node.args.args]

    forbidden_names = {
        "packet_history",
        "history",
        "shadow",
        "cache",
        "global_memory",
        "population",
        "replication",
        "knowledge_store",
        "fixture_id",
        "query_id",
        "expected_token",
        "packet_id",
        "token_id",
    }
    forbidden = sorted(names & forbidden_names)
    signature = [parameter.name for parameter in inspect.signature(export_slot).parameters.values()]
    signature_ok = signature == ["source_state", "slot_id"]
    source_signature_ok = export_parameters == ["source_state", "slot_id"]
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok and source_signature_ok else "FAIL",
        "forbidden_names": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": signature,
        "source_signature": export_parameters,
        "signature_ok": signature_ok and source_signature_ok,
    }


def invalid_state_cases() -> list[tuple[str, torch.Tensor]]:
    cases: list[tuple[str, torch.Tensor]] = []
    empty_value = torch.zeros(1, 16, dtype=torch.int64)
    empty_value[0, 0] = 1
    cases.append(("empty_slot_nonzero_value", empty_value))

    occupied_zero = torch.zeros(1, 16, dtype=torch.int64)
    occupied_zero[0, 8] = 1
    cases.append(("occupied_slot_zero_value", occupied_zero))

    invalid_occupancy = torch.zeros(1, 16, dtype=torch.int64)
    invalid_occupancy[0, 8] = 2
    cases.append(("invalid_occupancy_bit", invalid_occupancy))

    inconsistent_slot = torch.zeros(1, 16, dtype=torch.int64)
    inconsistent_slot[0, 0] = 2
    inconsistent_slot[0, 8] = 1
    cases.append(("value_slot_mismatch", inconsistent_slot))
    return cases


def run_characterization(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ids = packet_ids(bank)
    tokens = [ids[packet] for packet in config["exported_packets"]]
    source_cell, source_state = fresh_cell_state()
    source_state = write(source_cell, source_state, tokens)

    empty_cell, empty_state = fresh_cell_state()
    empty_slot = export_slot(empty_state, 0) is None
    single_cell, single_state = fresh_cell_state()
    single_state = write(single_cell, single_state, [tokens[1]])
    source_slot = tokens[1] % 8
    single_payload = export_slot(single_state, source_slot)
    single_target, single_target_state = fresh_cell_state()
    single_target_state = deliver_export(single_target, single_target_state, single_payload)
    single_export = {
        "source_slot": source_slot,
        "payload": single_payload,
        "target_contains": export_slot(single_target_state, source_slot) == single_payload,
    }

    wrong_slot = export_slot(single_state, (source_slot + 1) % 8) is None
    tampered = []
    for name, state in invalid_state_cases():
        try:
            export_slot(state, 0)
        except ValueError:
            tampered.append({"case": name, "failed_closed": True})
        else:
            tampered.append({"case": name, "failed_closed": False})

    full_target, full_target_state = fresh_cell_state()
    exported_payloads: list[int] = []
    for slot_id in range(config["required_slots"]):
        payload = export_slot(source_state, slot_id)
        if payload is None:
            raise AssertionError(f"full source slot {slot_id} unexpectedly empty")
        exported_payloads.append(payload)
        full_target_state = deliver_export(full_target, full_target_state, payload)
    full_export = {
        "exported_payloads": exported_payloads,
        "source_state_sha256": state_digest(source_state),
        "target_state_sha256": state_digest(full_target_state),
        "exact_state_copy": torch.equal(source_state, full_target_state),
        "target_slots": [export_slot(full_target_state, slot_id) for slot_id in range(config["required_slots"])],
    }

    interrupted_target, interrupted_state = fresh_cell_state()
    for slot_id in range(4):
        payload = export_slot(source_state, slot_id)
        if payload is None:
            raise AssertionError("interrupted export unexpectedly empty")
        interrupted_state = deliver_export(interrupted_target, interrupted_state, payload)
    source_payload = source_cell.serialize_state(source_state)
    target_payload = interrupted_target.serialize_state(interrupted_state)
    restored_source = KC1ACell().restore_state(source_payload, dtype=torch.int64, device=torch.device("cpu"))
    restored_target_cell = KC1ACell()
    restored_target_state = restored_target_cell.restore_state(target_payload, dtype=torch.int64, device=torch.device("cpu"))
    for slot_id in range(4, config["required_slots"]):
        payload = export_slot(restored_source, slot_id)
        if payload is None:
            raise AssertionError("remainder export unexpectedly empty")
        restored_target_state = deliver_export(restored_target_cell, restored_target_state, payload)
    interruption = {
        "source_state_bytes": len(source_payload),
        "target_state_bytes": len(target_payload),
        "target_state_sha256": state_digest(restored_target_state),
        "matches_uninterrupted": torch.equal(restored_target_state, full_target_state),
    }

    source_digest_before_loss = state_digest(source_state)
    del source_cell, source_state
    source_loss = {
        "target_retains_all": all(export_slot(full_target_state, slot_id) == exported_payloads[slot_id] for slot_id in range(config["required_slots"])),
        "target_state_sha256": state_digest(full_target_state),
        "source_state_sha256_before_destruction": source_digest_before_loss,
    }

    destination_loss_source, destination_loss_state = fresh_cell_state()
    destination_loss_state = write(destination_loss_source, destination_loss_state, [tokens[0]])
    lost_destination_cell, lost_destination_state = fresh_cell_state()
    del lost_destination_cell, lost_destination_state
    replacement_cell, replacement_state = fresh_cell_state()
    replacement_payload = export_slot(destination_loss_state, tokens[0] % 8)
    if replacement_payload is None:
        raise AssertionError("destination-loss source export unexpectedly empty")
    replacement_state = deliver_export(replacement_cell, replacement_state, replacement_payload)
    destination_loss = {
        "source_retains_before_transfer": export_slot(destination_loss_state, tokens[0] % 8) == tokens[0],
        "replacement_receives": export_slot(replacement_state, tokens[0] % 8) == tokens[0],
    }

    return {
        "empty_slot": {"returns_empty": empty_slot},
        "single_export": single_export,
        "wrong_slot_request": {"returns_empty": wrong_slot, "source_slot": source_slot},
        "tampered_state": tampered,
        "full_bank_export": full_export,
        "source_destruction": source_loss,
        "interruption_restart": interruption,
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
    export_audit = audit_export_source(EXPORT_PATH)
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
    first = run_characterization(bank, config)
    second = run_characterization(bank, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "coordinator_state_zero": resource_pass,
        "no_oracle_interface": export_audit["status"] == "PASS",
        "empty_slot": first["empty_slot"]["returns_empty"],
        "single_export": first["single_export"]["target_contains"],
        "wrong_slot_request": first["wrong_slot_request"]["returns_empty"],
        "tampered_state": all(row["failed_closed"] for row in first["tampered_state"]),
        "full_bank_export": first["full_bank_export"]["exact_state_copy"],
        "source_destruction": first["source_destruction"]["target_retains_all"],
        "interruption_restart": first["interruption_restart"]["matches_uninterrupted"],
        "destination_loss_before_transfer": first["destination_loss_before_transfer"]["source_retains_before_transfer"] and first["destination_loss_before_transfer"]["replacement_receives"],
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-2B-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_2B_DEV_COMPLETE" if passed else "KC_2B_DEV_INVALID",
        "cell_candidate_id": config["cell_candidate_id"],
        "cell_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "export_source_sha256": sha256(EXPORT_PATH),
        "anchor_errors": anchor_errors,
        "coordinator_resource": resource,
        "export_source_audit": export_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development oracle-free state export characterization only; reproduction, population, and scientific conclusions are forbidden.",
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
