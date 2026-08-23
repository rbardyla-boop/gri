#!/usr/bin/env python3
"""KC-2D-D bounded child creation characterization."""
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
from sim.kc2b.export import export_slot
from sim.kc2d.spawn import resource_manifest, spawn_child
import sim.kc2d.spawn as spawn_module

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
SPAWN_PATH = HERE / "spawn.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"
EXPORT_PATH = ROOT / "sim" / "kc2b" / "export.py"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_ids(bank: dict[str, Any]) -> dict[str, int]:
    return {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}


def fresh_parent() -> tuple[KC1ACell, torch.Tensor]:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    return cell, state


def write(cell: KC1ACell, state: torch.Tensor, tokens: list[int]) -> torch.Tensor:
    for token in tokens:
        state = cell.step(torch.tensor([token], dtype=torch.int64), state)
    return state


def occupied_tokens(state: torch.Tensor) -> list[int]:
    return [
        payload
        for slot_id in range(8)
        for payload in [export_slot(state, slot_id)]
        if payload is not None
    ]


def state_digest(state: torch.Tensor) -> str:
    return tensor_digest(state)


def audit_spawn_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    imports: set[str] = set()
    classes = 0
    global_statements = 0
    spawn_parameters: list[str] | None = None
    child_constructions = 0
    recursive_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, ast.Global):
            global_statements += 1
        elif isinstance(node, ast.FunctionDef) and node.name == "spawn_child":
            spawn_parameters = [argument.arg for argument in node.args.args]
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == "KC1ACell":
                        child_constructions += 1
                    if child.func.id == "spawn_child":
                        recursive_calls += 1

    forbidden_names = {
        "population",
        "registry",
        "network",
        "socket",
        "thread",
        "threads",
        "process",
        "processes",
        "subprocess",
        "timer",
        "timers",
        "scheduler",
        "filesystem",
        "persist",
        "persistence",
        "history",
        "queue",
        "automatic",
        "recursive",
    }
    forbidden = sorted((names | imports) & forbidden_names)
    runtime_signature = [parameter.name for parameter in inspect.signature(spawn_child).parameters.values()]
    expected_signature = ["parent_cell", "parent_state"]
    signature_ok = runtime_signature == expected_signature and spawn_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok and child_constructions == 1 and recursive_calls == 0 else "FAIL",
        "forbidden_names": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": runtime_signature,
        "source_signature": spawn_parameters,
        "signature_ok": signature_ok,
        "child_constructions_in_spawn": child_constructions,
        "recursive_spawn_calls": recursive_calls,
    }


def malformed_parent_check() -> bool:
    parent_cell, parent_state = fresh_parent()
    parent_state[0, 0] = 1
    try:
        spawn_child(parent_cell, parent_state)
    except ValueError:
        return True
    return False


def interrupted_spawn_check(parent_cell: KC1ACell, parent_state: torch.Tensor) -> dict[str, Any]:
    original_deliver = spawn_module.deliver_export
    calls = 0
    parent_digest_before = state_digest(parent_state)

    def fail_on_second_delivery(cell: KC1ACell, state: torch.Tensor, payload: int) -> torch.Tensor:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected bounded spawn interruption")
        return original_deliver(cell, state, payload)

    spawn_module.deliver_export = fail_on_second_delivery
    returned_child: tuple[KC1ACell, torch.Tensor] | None = None
    try:
        try:
            returned_child = spawn_child(parent_cell, parent_state)
        except RuntimeError:
            pass
    finally:
        spawn_module.deliver_export = original_deliver
    return {
        "failed_closed": returned_child is None and calls == 2,
        "parent_unchanged": state_digest(parent_state) == parent_digest_before,
        "delivery_calls_before_failure": calls,
    }


def characterize_once(bank: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ids = packet_ids(bank)
    partial_tokens = [ids["p000"], ids["p001"]]
    full_tokens = [ids[packet] for packet in ["p007", "p000", "p001", "p002", "p003", "p004", "p005", "p006"]]

    empty_parent_cell, empty_parent_state = fresh_parent()
    empty_child_cell, empty_child_state = spawn_child(empty_parent_cell, empty_parent_state)
    empty_parent = {
        "exact": torch.equal(empty_parent_state, empty_child_state),
        "child_tokens": occupied_tokens(empty_child_state),
    }

    partial_parent_cell, partial_parent_state = fresh_parent()
    partial_parent_state = write(partial_parent_cell, partial_parent_state, partial_tokens)
    partial_child_cell, partial_child_state = spawn_child(partial_parent_cell, partial_parent_state)
    partial_parent = {
        "exact": torch.equal(partial_parent_state, partial_child_state),
        "parent_tokens": occupied_tokens(partial_parent_state),
        "child_tokens": occupied_tokens(partial_child_state),
    }

    parent_cell, parent_state = fresh_parent()
    parent_state = write(parent_cell, parent_state, full_tokens)
    parent_digest_before = state_digest(parent_state)
    child_cell, child_state = spawn_child(parent_cell, parent_state)
    full_parent = {
        "exact": torch.equal(parent_state, child_state),
        "parent_digest": parent_digest_before,
        "child_digest": state_digest(child_state),
        "parent_tokens": occupied_tokens(parent_state),
        "child_tokens": occupied_tokens(child_state),
    }
    independent_storage = {
        "distinct_cells": parent_cell is not child_cell,
        "distinct_states": parent_state.data_ptr() != child_state.data_ptr(),
    }

    parent_mutated = parent_cell.step(torch.tensor([ids["p015"]], dtype=torch.int64), parent_state)
    child_before_child_mutation = child_state.detach().clone()
    child_mutated = child_cell.step(torch.tensor([ids["p016"]], dtype=torch.int64), child_state)
    mutation_isolation = {
        "parent_mutation_does_not_change_child": torch.equal(child_before_child_mutation, child_state),
        "child_mutation_does_not_change_parent": not torch.equal(parent_mutated, parent_state) and torch.equal(parent_state, write(parent_cell, parent_state, [])),
        "parent_mutated_tokens": occupied_tokens(parent_mutated),
        "child_mutated_tokens": occupied_tokens(child_mutated),
    }

    parent_for_loss_cell, parent_for_loss_state = fresh_parent()
    parent_for_loss_state = write(parent_for_loss_cell, parent_for_loss_state, full_tokens)
    retained_child_cell, retained_child_state = spawn_child(parent_for_loss_cell, parent_for_loss_state)
    del parent_for_loss_cell, parent_for_loss_state
    parent_destruction = {
        "child_survives": occupied_tokens(retained_child_state) == full_tokens,
        "child_state_digest": state_digest(retained_child_state),
    }

    interrupted = interrupted_spawn_check(parent_cell, parent_state)
    malformed = {"parent_failed_closed": malformed_parent_check()}

    restart_parent_cell, restart_parent_state = fresh_parent()
    restart_parent_state = write(restart_parent_cell, restart_parent_state, full_tokens)
    restart_payload = restart_parent_cell.serialize_state(restart_parent_state)
    restored_parent_cell = KC1ACell()
    restored_parent_state = restored_parent_cell.restore_state(restart_payload, dtype=torch.int64, device=torch.device("cpu"))
    restored_child_cell, restored_child_state = spawn_child(restored_parent_cell, restored_parent_state)
    restart_child_payload = restored_child_cell.serialize_state(restored_child_state)
    restart_child_restored = KC1ACell().restore_state(restart_child_payload, dtype=torch.int64, device=torch.device("cpu"))
    restart = {
        "parent_bytes": len(restart_payload),
        "child_bytes": len(restart_child_payload),
        "parent_spawn_matches": torch.equal(restored_child_state, child_before_child_mutation),
        "child_restart_matches": torch.equal(restart_child_restored, restored_child_state),
    }

    g0_cell, g0_state = fresh_parent()
    g0_state = write(g0_cell, g0_state, full_tokens)
    g1_cell, g1_state = spawn_child(g0_cell, g0_state)
    g2_cell, g2_state = spawn_child(g1_cell, g1_state)
    lineage = {
        "depth": 2,
        "g0_equals_g1": torch.equal(g0_state, g1_state),
        "g1_equals_g2": torch.equal(g1_state, g2_state),
        "g0_equals_g2": torch.equal(g0_state, g2_state),
        "g2_tokens": occupied_tokens(g2_state),
    }

    return {
        "empty_parent": empty_parent,
        "partial_parent": partial_parent,
        "full_parent": full_parent,
        "independent_storage": independent_storage,
        "mutation_isolation": mutation_isolation,
        "parent_destruction": parent_destruction,
        "malformed_parent": malformed,
        "interrupted_spawn": interrupted,
        "restart": restart,
        "lineage": lineage,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    anchor_errors = []
    if sha256(CELL_PATH) != config.get("cell_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(EXPORT_PATH) != config.get("export_source_sha256"):
        anchor_errors.append("KC-2B export source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    resource = resource_manifest()
    resource_pass = resource == {
        "coordinator_state_bytes": config["coordinator_state_bytes"],
        "coordinator_persistent_fields": config["coordinator_persistent_fields"],
        "children_created_per_call": config["children_created_per_call"],
        "automatic_spawn_calls": config["automatic_spawn_calls"],
        "population_registry": config["population_registry"],
        "uses_filesystem": False,
        "uses_network": False,
        "uses_threads": False,
        "uses_processes": False,
        "uses_timers": False,
        "uses_scheduler": False,
        "uses_replication": False,
    }
    source_audit = audit_spawn_source(SPAWN_PATH)
    first = characterize_once(bank, config)
    second = characterize_once(bank, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "resource_boundary": resource_pass,
        "source_signature_audit": source_audit["status"] == "PASS",
        "empty_parent": first["empty_parent"]["exact"] and first["empty_parent"]["child_tokens"] == [],
        "partial_parent": first["partial_parent"]["exact"],
        "full_parent": first["full_parent"]["exact"],
        "independent_storage": all(first["independent_storage"].values()),
        "mutation_isolation": first["mutation_isolation"]["parent_mutation_does_not_change_child"] and first["mutation_isolation"]["child_mutation_does_not_change_parent"],
        "parent_destruction": first["parent_destruction"]["child_survives"],
        "malformed_parent_fail_closed": first["malformed_parent"]["parent_failed_closed"],
        "interrupted_spawn_atomicity": first["interrupted_spawn"]["failed_closed"] and first["interrupted_spawn"]["parent_unchanged"],
        "restart": first["restart"]["parent_spawn_matches"] and first["restart"]["child_restart_matches"],
        "lineage_depth_two": first["lineage"]["depth"] == config["lineage_depth_max"] and first["lineage"]["g0_equals_g1"] and first["lineage"]["g1_equals_g2"] and first["lineage"]["g0_equals_g2"],
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-2D-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_2D_DEV_COMPLETE" if passed else "KC_2D_DEV_INVALID",
        "cell_candidate_id": config["cell_candidate_id"],
        "cell_source_sha256": sha256(CELL_PATH),
        "export_source_sha256": sha256(EXPORT_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "spawn_source_sha256": sha256(SPAWN_PATH),
        "anchor_errors": anchor_errors,
        "coordinator_resource": resource,
        "spawn_source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development bounded child-creation characterization only; reproduction, population, and scientific conclusions are forbidden.",
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
