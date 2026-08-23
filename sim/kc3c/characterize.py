#!/usr/bin/env python3
"""KC-3C-D local contact selection characterization."""
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
from sim.kc2b.export import export_slot
from sim.kc3a.manager import MAX_GENERATION, MAX_POPULATION, PopulationManager, REGISTRY_FIELDS, resource_manifest as population_resource
from sim.kc3b.share import resource_manifest as share_resource
from sim.kc3c.activate import activate_cell, resource_manifest
import sim.kc3c.activate as activate_module
from sim.runtime import canonical, tensor_digest

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
ACTIVATE_PATH = HERE / "activate.py"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
CHILD_PATH = ROOT / "sim" / "kc2d" / "spawn.py"
SHARE_PATH = ROOT / "sim" / "kc3b" / "share.py"
EXPORT_PATH = ROOT / "sim" / "kc2b" / "export.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_ids(bank: dict[str, Any]) -> dict[str, int]:
    return {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}


def state_tokens(state: torch.Tensor) -> list[int]:
    return [
        token
        for slot_id in range(8)
        for token in [export_slot(state, slot_id)]
        if token is not None
    ]


def population_snapshot(population: PopulationManager) -> dict[str, Any]:
    return {
        "registry": population.registry_snapshot(),
        "live_ids": population.live_ids(),
        "live_state_digests": population.live_state_digests(),
    }


def chain_population() -> tuple[PopulationManager, list[str]]:
    population = PopulationManager()
    ids = [population.create_founder()]
    # KC-3A freezes the maximum generation at 3, so a linear chain has
    # exactly four live cells: generations 0, 1, 2, and 3.
    for _ in range(3):
        ids.append(population.spawn(ids[-1]))
    return population, ids


def branch_population() -> tuple[PopulationManager, list[str]]:
    population = PopulationManager()
    founder = population.create_founder()
    first = population.spawn(founder)
    left = population.spawn(first)
    right = population.spawn(first)
    tail = population.spawn(right)
    return population, [founder, first, left, right, tail]


def audit_activate_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    classes = 0
    global_statements = 0
    activate_parameters: list[str] | None = None
    activate_state_snapshots = 0
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
        elif isinstance(node, ast.FunctionDef) and node.name == "activate_cell":
            activate_parameters = [argument.arg for argument in node.args.args]
            activate_state_snapshots = sum(
                1
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "state_snapshot"
            )
    forbidden = sorted((names | imports) & {
        "packet_id", "token_id", "expected_value", "knowledge", "history", "cache",
        "shadow", "routing", "fitness", "selection", "network", "socket", "thread",
        "process", "subprocess", "timer", "scheduler", "target_state", "target_cache",
    })
    runtime_signature = [parameter.name for parameter in inspect.signature(activate_cell).parameters.values()]
    expected_signature = ["population", "source_id"]
    signature_ok = runtime_signature == expected_signature and activate_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok and activate_state_snapshots == 1 else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": runtime_signature,
        "source_signature": activate_parameters,
        "signature_ok": signature_ok,
        "direct_state_snapshot_calls_in_activate": activate_state_snapshots,
    }


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    packet = ids["p007"]
    second_packet = ids["p000"]
    conflict = ids["p015"]

    linear, linear_cells = chain_population()
    c0, c1, c2, c3 = linear_cells
    pre_birth = {cell_id: state_tokens(linear.state_snapshot(cell_id)) for cell_id in linear_cells}
    linear.consume(c0, packet)
    post_birth = {
        "all_empty_before": all(tokens == [] for tokens in pre_birth.values()),
        "only_source_after": state_tokens(linear.state_snapshot(c0)) == [packet] and all(state_tokens(linear.state_snapshot(cell_id)) == [] for cell_id in linear_cells[1:]),
    }
    activation_c0 = activate_cell(linear, c0)
    activation_c1 = activate_cell(linear, c1)
    c3_empty_before_c2 = packet not in state_tokens(linear.state_snapshot(c3))
    activation_c2 = activate_cell(linear, c2)
    linear_wave = {
        "c0_to_c1": packet in state_tokens(linear.state_snapshot(c1)),
        "c1_to_c2": packet in state_tokens(linear.state_snapshot(c2)),
        "c2_to_c3": packet in state_tokens(linear.state_snapshot(c3)),
        "c3_empty_before_c2": c3_empty_before_c2,
        "activation_neighbors": [activation_c0["neighbor_ids"], activation_c1["neighbor_ids"], activation_c2["neighbor_ids"]],
    }

    branch, branch_cells = branch_population()
    b0, b1, b2, b3, b4 = branch_cells
    branch.consume(b0, packet)
    branch_activation_0 = activate_cell(branch, b0)
    branch_activation_1 = activate_cell(branch, b1)
    branching = {
        "parent_activation_targets_children": sorted(branch_activation_1["neighbor_ids"]) == sorted([b0, b2, b3]),
        "left_has_packet": packet in state_tokens(branch.state_snapshot(b2)),
        "right_has_packet": packet in state_tokens(branch.state_snapshot(b3)),
        "tail_empty_before_secondary": packet not in state_tokens(branch.state_snapshot(b4)),
        "branch_parent_activation": branch_activation_0["neighbor_ids"] == [b1],
    }
    branch_activation_3 = activate_cell(branch, b3)
    secondary = {
        "tail_contacted_by_received_child": branch_activation_3["neighbor_ids"] == [b1, b4],
        "tail_receives_from_branch": packet in state_tokens(branch.state_snapshot(b4)),
    }

    dead, dead_cells = branch_population()
    dead_source, dead_middle, dead_left, dead_right, dead_tail = dead_cells
    dead.kill(dead_left)
    dead.consume(dead_middle, packet)
    dead_activation = activate_cell(dead, dead_middle)
    dead_neighbor = {
        "dead_parent_or_child_ignored": dead_activation["neighbor_ids"] == [dead_source, dead_right],
        "dead_not_resurrected": dead_left not in dead.live_ids(),
        "survivors_unchanged_lifecycle": all(row["alive"] for row in dead.registry_snapshot() if row["cell_id"] in [dead_source, dead_middle, dead_right, dead_tail]),
    }

    empty, empty_cells = chain_population()
    empty_source = empty_cells[0]
    empty_before = population_snapshot(empty)
    empty_activation = activate_cell(empty, empty_source)
    empty_source_result = {
        "contact_count": empty_activation["contact_count"] == 0,
        "population_unchanged": population_snapshot(empty) == empty_before,
    }

    partial, partial_cells = chain_population()
    partial_source, partial_target = partial_cells[:2]
    partial.consume(partial_source, packet)
    partial_before = population_snapshot(partial)
    partial_activation = activate_cell(partial, partial_source)
    partial_source_result = {
        "one_slot": partial_activation["occupied_slot_count"] == 1,
        "target_has_only_packet": state_tokens(partial.state_snapshot(partial_target)) == [packet],
        "registry_unchanged": partial.registry_snapshot() == partial_before["registry"],
    }

    multi, multi_cells = chain_population()
    multi_source, multi_target = multi_cells[:2]
    multi.consume(multi_source, packet)
    multi.consume(multi_source, second_packet)
    multi_activation = activate_cell(multi, multi_source)
    multi_packet_result = {
        "two_slots_discovered": multi_activation["occupied_slot_count"] == 2,
        "target_has_both": sorted(state_tokens(multi.state_snapshot(multi_target))) == sorted([packet, second_packet]),
    }

    collision, collision_cells = chain_population()
    collision_source, collision_target = collision_cells[:2]
    collision.consume(collision_source, packet)
    collision.consume(collision_target, conflict)
    collision_activation = activate_cell(collision, collision_source)
    collision_result = {
        "one_slot_contact": collision_activation["contact_count"] == 1,
        "shared_replaces_conflict": packet in state_tokens(collision.state_snapshot(collision_target)) and conflict not in state_tokens(collision.state_snapshot(collision_target)),
    }

    duplicate, duplicate_cells = chain_population()
    duplicate_source, duplicate_target = duplicate_cells[:2]
    duplicate.consume(duplicate_source, packet)
    activate_cell(duplicate, duplicate_source)
    duplicate_before = population_snapshot(duplicate)
    activate_cell(duplicate, duplicate_source)
    duplicate_result = {"state_unchanged": population_snapshot(duplicate) == duplicate_before}

    source_death, source_death_cells = chain_population()
    sd0, sd1, sd2, sd3 = source_death_cells
    source_death.consume(sd0, packet)
    activate_cell(source_death, sd0)
    source_death.kill(sd0)
    activate_cell(source_death, sd1)
    activate_cell(source_death, sd2)
    source_death_result = {
        "source_dead": sd0 not in source_death.live_ids(),
        "descendant_continues": packet in state_tokens(source_death.state_snapshot(sd3)),
    }

    last_copy, last_copy_cells = chain_population()
    lc0, lc1, _, _ = last_copy_cells
    last_copy.consume(lc0, packet)
    activate_cell(last_copy, lc0)
    last_copy.kill(lc0)
    last_copy.kill(lc1)
    last_copy_payload = json.loads(last_copy.serialize().decode("utf-8"))
    last_copy_result = {
        "no_live_cell_contains_packet": all(packet not in state_tokens(last_copy.state_snapshot(cell_id)) for cell_id in last_copy.live_ids()),
        "registry_cannot_reconstruct": str(packet) not in str(last_copy_payload["registry"]),
        "registry_fields_only": all(set(row) == set(REGISTRY_FIELDS) for row in last_copy_payload["registry"]),
    }

    metadata, metadata_cells = chain_population()
    metadata_source = metadata_cells[0]
    metadata.consume(metadata_source, packet)
    registry_before = metadata.registry_snapshot()
    live_before = metadata.live_ids()
    activate_cell(metadata, metadata_source)
    registry_immutability = {
        "registry_unchanged": metadata.registry_snapshot() == registry_before,
        "generation_values": [row["generation"] for row in metadata.registry_snapshot()],
    }
    population_immutability = {
        "live_ids_unchanged": metadata.live_ids() == live_before,
        "population_count": len(metadata.live_ids()),
    }

    capped, capped_cells = chain_population()
    cap_source = capped_cells[0]
    while len(capped.live_ids()) < MAX_POPULATION:
        capped_cells.append(capped.spawn(cap_source))
    cap_before_failed_spawn = population_snapshot(capped)
    try:
        capped.spawn(cap_source)
    except ValueError:
        cap_rejected = True
    else:
        cap_rejected = False
    cap_after_failed_spawn = population_snapshot(capped)
    capped.consume(cap_source, packet)
    cap_before = population_snapshot(capped)
    activate_cell(capped, cap_source)
    population_cap = {
        "at_cap": len(capped.live_ids()) == MAX_POPULATION,
        "cap_rejected": cap_rejected and cap_after_failed_spawn == cap_before_failed_spawn,
        "registry_unchanged": capped.registry_snapshot() == cap_before["registry"],
        "live_ids_unchanged": capped.live_ids() == cap_before["live_ids"],
    }

    restart, restart_cells = chain_population()
    r0, r1, r2, r3 = restart_cells
    restart.consume(r0, packet)
    activate_cell(restart, r0)
    restart_payload = restart.serialize()
    restored = PopulationManager.restore(restart_payload)
    activate_cell(restart, r1)
    activate_cell(restart, r2)
    activate_cell(restored, r1)
    activate_cell(restored, r2)
    mid_wave_restart = {
        "registry_equal": restored.registry_snapshot() == restart.registry_snapshot(),
        "live_ids_equal": restored.live_ids() == restart.live_ids(),
        "state_digests_equal": restored.live_state_digests() == restart.live_state_digests(),
        "tail_has_packet": packet in state_tokens(restored.state_snapshot(r3)),
    }

    no_policy, no_policy_cells = chain_population()
    no_policy_source = no_policy_cells[0]
    no_policy.consume(no_policy_source, packet)
    before_no_policy = len(no_policy.live_ids())
    activate_cell(no_policy, no_policy_source)
    no_automatic = {
        "explicit_only_count_unchanged": len(no_policy.live_ids()) == before_no_policy,
        "uncontacted_tail_empty": packet not in state_tokens(no_policy.state_snapshot(no_policy_cells[2])),
    }

    return {
        "post_birth_acquisition": post_birth,
        "linear_wave": linear_wave,
        "branching_wave": branching,
        "secondary_propagation": secondary,
        "dead_neighbor": dead_neighbor,
        "empty_source": empty_source_result,
        "partial_source": partial_source_result,
        "multi_packet_source": multi_packet_result,
        "collision": collision_result,
        "duplicate_activation": duplicate_result,
        "source_death": source_death_result,
        "last_copy_death": last_copy_result,
        "registry_immutability": registry_immutability,
        "population_immutability": population_immutability,
        "population_cap": population_cap,
        "mid_wave_restart": mid_wave_restart,
        "no_automatic_activation": no_automatic,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    anchor_errors = []
    if sha256(MANAGER_PATH) != config.get("manager_source_sha256"):
        anchor_errors.append("KC-3A manager source hash mismatch")
    if sha256(CHILD_PATH) != config.get("child_creation_source_sha256"):
        anchor_errors.append("KC-2D child source hash mismatch")
    if sha256(SHARE_PATH) != config.get("share_source_sha256"):
        anchor_errors.append("KC-3B share source hash mismatch")
    if sha256(EXPORT_PATH) != config.get("export_source_sha256"):
        anchor_errors.append("KC-2B export source hash mismatch")
    if sha256(CELL_PATH) != config.get("cell_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    resource = resource_manifest()
    resource_pass = resource == {
        "policy_state_bytes": config["policy_state_bytes"],
        "persistent_policy_fields": config["persistent_policy_fields"],
        "automatic_activation": config["automatic_activation"],
        "automatic_contacts": config["automatic_contacts"],
        "creates_children": config["creates_children"],
        "target_state_policy_inspection": config["target_state_policy_inspection"],
        "knowledge_map": config["knowledge_map"],
        "registry_mutation": False,
    }
    source_audit = audit_activate_source(ACTIVATE_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "source_signature_audit": source_audit["status"] == "PASS",
        "zero_policy_state": resource_pass,
        "post_birth_acquisition": all(first["post_birth_acquisition"].values()),
        "linear_wave": all(first["linear_wave"][key] for key in ["c0_to_c1", "c1_to_c2", "c2_to_c3", "c3_empty_before_c2"]),
        "branching_wave": all(first["branching_wave"].values()),
        "secondary_propagation": all(first["secondary_propagation"].values()),
        "dead_neighbor": all(first["dead_neighbor"].values()),
        "empty_source": all(first["empty_source"].values()),
        "partial_source": all(first["partial_source"].values()),
        "multi_packet_source": all(first["multi_packet_source"].values()),
        "collision": all(first["collision"].values()),
        "duplicate_activation": all(first["duplicate_activation"].values()),
        "source_death": all(first["source_death"].values()),
        "last_copy_death": all(first["last_copy_death"].values()),
        "registry_immutability": first["registry_immutability"]["registry_unchanged"],
        "population_immutability": all(first["population_immutability"].values()),
        "population_cap": all(first["population_cap"].values()),
        "mid_wave_restart": all(first["mid_wave_restart"].values()),
        "no_automatic_activation": all(first["no_automatic_activation"].values()),
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3C-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3C_DEV_COMPLETE" if passed else "KC_3C_DEV_INVALID",
        "manager_source_sha256": sha256(MANAGER_PATH),
        "child_creation_source_sha256": sha256(CHILD_PATH),
        "share_source_sha256": sha256(SHARE_PATH),
        "export_source_sha256": sha256(EXPORT_PATH),
        "cell_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "activate_source_sha256": sha256(ACTIVATE_PATH),
        "anchor_errors": anchor_errors,
        "resource_manifest": resource,
        "activate_source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development local contact-selection characterization only; automatic activation, selection, and scientific conclusions are forbidden.",
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
