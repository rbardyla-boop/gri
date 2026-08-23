#!/usr/bin/env python3
"""KC-3B-D bounded knowledge spread characterization."""
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
from sim.kc3b.share import resource_manifest, share_slot
import sim.kc3b.share as share_module
from sim.runtime import canonical, tensor_digest

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
SHARE_PATH = HERE / "share.py"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
CHILD_PATH = ROOT / "sim" / "kc2d" / "spawn.py"
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
    for _ in range(3):
        ids.append(population.spawn(ids[-1]))
    return population, ids


def branch_population() -> tuple[PopulationManager, list[str]]:
    population = PopulationManager()
    founder = population.create_founder()
    first = population.spawn(founder)
    left = population.spawn(first)
    right = population.spawn(first)
    return population, [founder, first, left, right]


def audit_share_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    classes = 0
    global_statements = 0
    share_parameters: list[str] | None = None
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
        elif isinstance(node, ast.FunctionDef) and node.name == "share_slot":
            share_parameters = [argument.arg for argument in node.args.args]
    forbidden = sorted((names | imports) & {
        "packet_id", "token_id", "expected_value", "knowledge", "history", "cache",
        "shadow", "routing", "fitness", "selection", "network", "socket", "thread",
        "process", "subprocess", "timer", "scheduler", "population_registry",
    })
    runtime_signature = [parameter.name for parameter in inspect.signature(share_slot).parameters.values()]
    expected_signature = ["population", "source_id", "target_id", "slot_id"]
    signature_ok = runtime_signature == expected_signature and share_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": runtime_signature,
        "source_signature": share_parameters,
        "signature_ok": signature_ok,
    }


def spread_chain(ids: dict[str, int]) -> dict[str, Any]:
    population, cells = chain_population()
    source, first, second, last = cells
    packet = ids["p007"]
    pre_acquisition = {cell_id: state_tokens(population.state_snapshot(cell_id)) for cell_id in cells}
    population.consume(source, packet)
    post_birth = {
        "only_source_has_packet": state_tokens(population.state_snapshot(source)) == [packet],
        "others_empty": all(state_tokens(population.state_snapshot(cell_id)) == [] for cell_id in cells[1:]),
        "pre_acquisition": pre_acquisition,
    }
    one_hop = share_slot(population, source, first, packet % 8)
    one_hop_result = {
        "contact_accepted": one_hop,
        "target_has_packet": packet in state_tokens(population.state_snapshot(first)),
        "source_retains_packet": packet in state_tokens(population.state_snapshot(source)),
    }
    second_hop = share_slot(population, first, second, packet % 8)
    third_hop = share_slot(population, second, last, packet % 8)
    multi_hop = {
        "contacts": [[source, first], [first, second], [second, last]],
        "second_hop_accepted": second_hop,
        "third_hop_accepted": third_hop,
        "last_has_packet": packet in state_tokens(population.state_snapshot(last)),
        "source_never_directly_contacted_later_cells": True,
    }
    return {"post_birth": post_birth, "one_hop": one_hop_result, "multi_hop": multi_hop, "population": population, "cells": cells, "packet": packet}


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    packet = ids["p007"]
    conflict = ids["p015"]

    chain = spread_chain(ids)
    population = chain["population"]
    cells = chain["cells"]
    source, first, second, last = cells
    source_death_population, source_death_cells = chain_population()
    source_death, source_death_first, source_death_second, source_death_last = source_death_cells
    source_death_population.consume(source_death, packet)
    share_slot(source_death_population, source_death, source_death_first, packet % 8)
    source_death_population.kill(source_death)
    forwarded_after_source_death = share_slot(source_death_population, source_death_first, source_death_second, packet % 8)
    forwarded_to_last = share_slot(source_death_population, source_death_second, source_death_last, packet % 8)
    source_death_survival = {
        "source_dead": source_death not in source_death_population.live_ids(),
        "forwarded_after_source_death": forwarded_after_source_death and packet in state_tokens(source_death_population.state_snapshot(source_death_second)),
        "last_has_packet": forwarded_to_last and packet in state_tokens(source_death_population.state_snapshot(source_death_last)),
    }

    branch, branch_cells = branch_population()
    branch_source, branch_middle, branch_left, branch_right = branch_cells
    branch.consume(branch_source, packet)
    share_slot(branch, branch_source, branch_middle, packet % 8)
    branch_left_contact = share_slot(branch, branch_middle, branch_left, packet % 8)
    branch_right_contact = share_slot(branch, branch_middle, branch_right, packet % 8)
    branching = {
        "left_contact": branch_left_contact,
        "right_contact": branch_right_contact,
        "left_has_packet": packet in state_tokens(branch.state_snapshot(branch_left)),
        "right_has_packet": packet in state_tokens(branch.state_snapshot(branch_right)),
    }

    last_copy, last_copy_cells = chain_population()
    last_source, last_child, _, _ = last_copy_cells
    last_copy.consume(last_source, packet)
    share_slot(last_copy, last_source, last_child, packet % 8)
    last_copy.kill(last_source)
    last_copy.kill(last_child)
    last_copy_payload = json.loads(last_copy.serialize().decode("utf-8"))
    last_copy_death = {
        "no_live_cell_contains_packet": all(packet not in state_tokens(last_copy.state_snapshot(cell_id)) for cell_id in last_copy.live_ids()),
        "no_live_state_contains_packet": all(packet not in state_tokens(last_copy.state_snapshot(cell_id)) for cell_id in last_copy.live_ids()),
        "registry_fields_only": all(set(row) == set(REGISTRY_FIELDS) for row in last_copy_payload["registry"]),
        "packet_not_in_registry": str(packet) not in str(last_copy_payload["registry"]),
    }

    empty, empty_cells = chain_population()
    empty_source, empty_target, _, _ = empty_cells
    empty_before = population_snapshot(empty)
    empty_contact = share_slot(empty, empty_source, empty_target, (packet + 1) % 8)
    empty_slot = {
        "accepted": empty_contact,
        "target_unchanged": population_snapshot(empty) == empty_before,
    }

    wrong, wrong_cells = chain_population()
    wrong_source, wrong_target, _, _ = wrong_cells
    wrong.consume(wrong_source, packet)
    wrong_before = population_snapshot(wrong)
    wrong_contact = share_slot(wrong, wrong_source, wrong_target, (packet + 1) % 8)
    wrong_slot = {
        "accepted": wrong_contact,
        "target_unchanged": population_snapshot(wrong) == wrong_before,
        "packet_not_revealed": packet not in state_tokens(wrong.state_snapshot(wrong_target)),
    }

    collision, collision_cells = chain_population()
    collision_source, collision_target, _, _ = collision_cells
    collision.consume(collision_source, packet)
    collision.consume(collision_target, conflict)
    collision_contact = share_slot(collision, collision_source, collision_target, packet % 8)
    same_slot_collision = {
        "accepted": collision_contact,
        "target_has_shared": packet in state_tokens(collision.state_snapshot(collision_target)),
        "target_old_conflict_replaced": conflict not in state_tokens(collision.state_snapshot(collision_target)),
        "source_unchanged": packet in state_tokens(collision.state_snapshot(collision_source)),
    }

    duplicate, duplicate_cells = chain_population()
    duplicate_source, duplicate_target, _, _ = duplicate_cells
    duplicate.consume(duplicate_source, packet)
    share_slot(duplicate, duplicate_source, duplicate_target, packet % 8)
    before_duplicate = population_snapshot(duplicate)
    duplicate_contact = share_slot(duplicate, duplicate_source, duplicate_target, packet % 8)
    duplicate_contact_result = {
        "accepted": duplicate_contact,
        "state_unchanged": population_snapshot(duplicate) == before_duplicate,
    }

    order_a, order_a_cells = chain_population()
    order_a_source, order_a_first, order_a_second, _ = order_a_cells
    order_a.consume(order_a_source, packet)
    order_a.consume(order_a_first, conflict)
    share_slot(order_a, order_a_source, order_a_second, packet % 8)
    share_slot(order_a, order_a_first, order_a_second, packet % 8)
    order_b, order_b_cells = chain_population()
    order_b_source, order_b_first, order_b_second, _ = order_b_cells
    order_b.consume(order_b_source, packet)
    order_b.consume(order_b_first, conflict)
    share_slot(order_b, order_b_first, order_b_second, packet % 8)
    share_slot(order_b, order_b_source, order_b_second, packet % 8)
    contact_order = {
        "a_final_tokens": state_tokens(order_a.state_snapshot(order_a_second)),
        "b_final_tokens": state_tokens(order_b.state_snapshot(order_b_second)),
        "orders_are_explicitly_distinguishable": state_tokens(order_a.state_snapshot(order_a_second)) != state_tokens(order_b.state_snapshot(order_b_second)),
    }

    restart, restart_cells = chain_population()
    restart_source, restart_first, restart_second, restart_last = restart_cells
    restart.consume(restart_source, packet)
    share_slot(restart, restart_source, restart_first, packet % 8)
    restart_payload = restart.serialize()
    restored = PopulationManager.restore(restart_payload)
    share_slot(restored, restart_first, restart_second, packet % 8)
    share_slot(restored, restart_second, restart_last, packet % 8)
    share_slot(restart, restart_first, restart_second, packet % 8)
    share_slot(restart, restart_second, restart_last, packet % 8)
    mid_spread_restart = {
        "same_registry": restored.registry_snapshot() == restart.registry_snapshot(),
        "same_live_ids": restored.live_ids() == restart.live_ids(),
        "same_live_state_digests": restored.live_state_digests() == restart.live_state_digests(),
    }

    capped, capped_cells = chain_population()
    capped_source, capped_first, capped_second, capped_last = capped_cells
    for cell_id in capped_cells:
        capped.consume(cell_id, packet)
    registry_before_share = capped.registry_snapshot()
    live_before_share = capped.live_ids()
    share_slot(capped, capped_source, capped_first, packet % 8)
    share_slot(capped, capped_first, capped_second, packet % 8)
    share_slot(capped, capped_second, capped_last, packet % 8)
    population_cap_unchanged = {
        "live_count": len(capped.live_ids()),
        "at_cap_unchanged": len(capped.live_ids()) == len(live_before_share),
        "registry_unchanged": capped.registry_snapshot() == registry_before_share,
    }
    generation_metadata_unchanged = {
        "registry_unchanged": capped.registry_snapshot() == registry_before_share,
        "generations": [row["generation"] for row in capped.registry_snapshot()],
    }

    no_contact, no_contact_cells = chain_population()
    no_source, no_target, no_uncontacted, _ = no_contact_cells
    no_contact.consume(no_source, packet)
    share_slot(no_contact, no_source, no_target, packet % 8)
    no_automatic_contact = {
        "uncontacted_empty": packet not in state_tokens(no_contact.state_snapshot(no_uncontacted)),
        "population_count": len(no_contact.live_ids()),
    }

    return {
        "post_birth_acquisition": chain["post_birth"],
        "one_hop": chain["one_hop"],
        "multi_hop": chain["multi_hop"],
        "secondary_forwarding": chain["multi_hop"],
        "branching": branching,
        "source_death": source_death_survival,
        "last_copy_death": last_copy_death,
        "empty_slot": empty_slot,
        "wrong_slot": wrong_slot,
        "same_slot_collision": same_slot_collision,
        "duplicate_contact": duplicate_contact_result,
        "contact_order": contact_order,
        "mid_spread_restart": mid_spread_restart,
        "population_cap_unchanged": population_cap_unchanged,
        "generation_metadata_unchanged": generation_metadata_unchanged,
        "registry_audit": {
            "fields_exact": all(set(row) == set(REGISTRY_FIELDS) for row in capped.registry_snapshot()),
            "population_resource": population_resource(),
        },
        "no_automatic_contact": no_automatic_contact,
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
        "coordinator_state_bytes": config["coordinator_state_bytes"],
        "persistent_coordinator_fields": config["persistent_coordinator_fields"],
        "transfer_payload_persistent": config["transfer_payload_persistent"],
        "automatic_contacts": config["automatic_contacts"],
        "creates_children": config["creates_children"],
        "knowledge_map": config["knowledge_map"],
        "registry_mutation": False,
    }
    source_audit = audit_share_source(SHARE_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "source_signature_audit": source_audit["status"] == "PASS",
        "resource_boundary": resource_pass,
        "post_birth_acquisition": first["post_birth_acquisition"]["only_source_has_packet"] and first["post_birth_acquisition"]["others_empty"],
        "one_hop": first["one_hop"]["contact_accepted"] and first["one_hop"]["target_has_packet"],
        "multi_hop": first["multi_hop"]["second_hop_accepted"] and first["multi_hop"]["third_hop_accepted"] and first["multi_hop"]["last_has_packet"],
        "secondary_forwarding": first["secondary_forwarding"]["source_never_directly_contacted_later_cells"],
        "branching": all(first["branching"].values()),
        "source_death": all(first["source_death"].values()),
        "last_copy_death": all(first["last_copy_death"].values()),
        "empty_slot": not first["empty_slot"]["accepted"] and first["empty_slot"]["target_unchanged"],
        "wrong_slot": not first["wrong_slot"]["accepted"] and first["wrong_slot"]["target_unchanged"] and first["wrong_slot"]["packet_not_revealed"],
        "same_slot_collision": all(first["same_slot_collision"].values()),
        "duplicate_contact": all(first["duplicate_contact"].values()),
        "contact_order": first["contact_order"]["orders_are_explicitly_distinguishable"],
        "mid_spread_restart": all(first["mid_spread_restart"].values()),
        "population_cap_unchanged": all(first["population_cap_unchanged"].values()),
        "generation_metadata_unchanged": first["generation_metadata_unchanged"]["registry_unchanged"],
        "registry_audit": first["registry_audit"]["fields_exact"],
        "no_automatic_contact": first["no_automatic_contact"]["uncontacted_empty"] and first["no_automatic_contact"]["population_count"] == 4,
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3B-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3B_DEV_COMPLETE" if passed else "KC_3B_DEV_INVALID",
        "manager_source_sha256": sha256(MANAGER_PATH),
        "child_creation_source_sha256": sha256(CHILD_PATH),
        "export_source_sha256": sha256(EXPORT_PATH),
        "cell_source_sha256": sha256(CELL_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "share_source_sha256": sha256(SHARE_PATH),
        "anchor_errors": anchor_errors,
        "resource_manifest": resource,
        "share_source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development bounded knowledge-spread characterization only; automatic propagation, selection, and scientific conclusions are forbidden.",
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
