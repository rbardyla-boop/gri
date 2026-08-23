#!/usr/bin/env python3
"""KC-3A-D bounded population lifecycle characterization."""
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
from sim.kc2d.spawn import spawn_child
from sim.kc3a.manager import MAX_GENERATION, MAX_POPULATION, PopulationManager, REGISTRY_FIELDS, resource_manifest
import sim.kc3a.manager as manager_module
from sim.runtime import canonical, tensor_digest

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
MANAGER_PATH = HERE / "manager.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"
EXPORT_PATH = ROOT / "sim" / "kc2b" / "export.py"
CHILD_PATH = ROOT / "sim" / "kc2d" / "spawn.py"


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


def audit_manager_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    external_forbidden = {
        "network", "socket", "thread", "threads", "process", "processes", "subprocess",
        "timer", "timers", "scheduler", "filesystem", "persist", "persistence", "fitness",
        "selection", "mutation_at_birth", "automatic_spawn", "shadow", "routing", "knowledge_store",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(alias.name.split(".")[0] for alias in node.names)
    forbidden = sorted((names | imports) & external_forbidden)
    registry_fields = list(REGISTRY_FIELDS)
    return {
        "status": "PASS" if not forbidden and registry_fields == ["cell_id", "parent_id", "generation", "alive"] else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "registry_fields": registry_fields,
        "registry_fields_exact": registry_fields == ["cell_id", "parent_id", "generation", "alive"],
        "manager_signature": list(inspect.signature(PopulationManager).parameters),
    }


def registry_safe(manager: PopulationManager) -> bool:
    rows = manager.registry_snapshot()
    return all(set(row) == set(REGISTRY_FIELDS) for row in rows)


def manager_snapshot(manager: PopulationManager) -> dict[str, Any]:
    return {
        "registry": manager.registry_snapshot(),
        "live_ids": manager.live_ids(),
        "live_state_digests": manager.live_state_digests(),
    }


def schedule_snapshot(ids: dict[str, int]) -> dict[str, Any]:
    manager = PopulationManager()
    founder = manager.create_founder()
    manager.consume(founder, ids["p007"])
    first = manager.spawn(founder)
    second = manager.spawn(founder)
    manager.consume(first, ids["p000"])
    manager.spawn(first)
    manager.kill(second)
    return manager_snapshot(manager)


def malformed_restore_payload(manager: PopulationManager) -> bool:
    document = json.loads(manager.serialize().decode("utf-8"))
    document["registry"][0]["slot"] = 0
    try:
        PopulationManager.restore(canonical(document).encode("utf-8"))
    except ValueError:
        return True
    return False


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    founder_manager = PopulationManager()
    founder = founder_manager.create_founder()
    founder_creation = {
        "founder_id": founder,
        "live_count": len(founder_manager.live_ids()),
        "registry_safe": registry_safe(founder_manager),
    }

    founder_manager.consume(founder, ids["p007"])
    child = founder_manager.spawn(founder)
    exact_inheritance = {
        "parent_id": founder,
        "child_id": child,
        "parent_state_tokens": state_tokens(founder_manager.state_snapshot(founder)),
        "child_state_tokens": state_tokens(founder_manager.state_snapshot(child)),
        "equal_at_birth": founder_manager.state_snapshot(founder).equal(founder_manager.state_snapshot(child)),
    }
    parent_before_child_mutation = founder_manager.state_snapshot(founder)
    founder_manager.consume(child, ids["p000"])
    independent_divergence = {
        "parent_unchanged": torch.equal(parent_before_child_mutation, founder_manager.state_snapshot(founder)),
        "child_diverged": not torch.equal(parent_before_child_mutation, founder_manager.state_snapshot(child)),
    }
    child_before_parent_mutation = founder_manager.state_snapshot(child)
    founder_manager.consume(founder, ids["p015"])
    independent_divergence["child_unchanged"] = torch.equal(child_before_parent_mutation, founder_manager.state_snapshot(child))

    first_child = founder_manager.spawn(founder)
    second_child = founder_manager.spawn(child)
    multi_parent = {
        "first_child_parent": founder_manager.registry_snapshot()[2]["parent_id"],
        "second_parent": founder_manager.registry_snapshot()[3]["parent_id"],
        "distinct_children": first_child != second_child,
    }

    lineage_records = founder_manager.registry_snapshot()
    lineage = {
        "founder_generation": lineage_records[0]["generation"],
        "first_child_generation": lineage_records[1]["generation"],
        "grandchild_generation": founder_manager.registry_snapshot()[3]["generation"],
        "parent_links_present": all(set(record) == set(REGISTRY_FIELDS) for record in lineage_records),
    }

    cap_manager = PopulationManager()
    cap_founder = cap_manager.create_founder()
    cap_children = [cap_manager.spawn(cap_founder) for _ in range(MAX_POPULATION - 1)]
    cap_before = canonical(manager_snapshot(cap_manager))
    try:
        cap_manager.spawn(cap_founder)
        cap_failed = False
    except ValueError:
        cap_failed = True
    population_cap = {
        "live_count_before_attempt": len(cap_manager.live_ids()),
        "cap_children": cap_children,
        "failed_closed": cap_failed,
        "unchanged": canonical(manager_snapshot(cap_manager)) == cap_before,
    }

    generation_manager = PopulationManager()
    generation_ids = [generation_manager.create_founder()]
    for _ in range(MAX_GENERATION):
        generation_ids.append(generation_manager.spawn(generation_ids[-1]))
    try:
        generation_manager.spawn(generation_ids[-1])
        generation_failed = False
    except ValueError:
        generation_failed = True
    generation_cap = {
        "lineage": generation_ids,
        "max_generation": max(record["generation"] for record in generation_manager.registry_snapshot()),
        "failed_closed": generation_failed,
    }

    death_manager = PopulationManager()
    death_founder = death_manager.create_founder()
    death_manager.consume(death_founder, ids["p007"])
    death_child = death_manager.spawn(death_founder)
    survivor_before = death_manager.state_snapshot(death_child)
    death_manager.kill(death_founder)
    cell_death = {
        "founder_dead": death_manager.registry_snapshot()[0]["alive"] is False,
        "survivor_alive": death_child in death_manager.live_ids(),
        "survivor_unchanged": torch.equal(survivor_before, death_manager.state_snapshot(death_child)),
    }

    all_dead_manager = PopulationManager()
    all_dead_founder = all_dead_manager.create_founder()
    all_dead_manager.consume(all_dead_founder, ids["p007"])
    all_dead_child = all_dead_manager.spawn(all_dead_founder)
    all_dead_manager.kill(all_dead_founder)
    all_dead_manager.kill(all_dead_child)
    dead_payload = all_dead_manager.serialize()
    dead_document = json.loads(dead_payload.decode("utf-8"))
    knowledge_containment = {
        "no_live_cells": all_dead_manager.live_ids() == [],
        "no_live_state_payloads": dead_document["live_states"] == {},
        "registry_safe": registry_safe(all_dead_manager),
        "registry_has_no_state_fields": all(set(row) == set(REGISTRY_FIELDS) for row in dead_document["registry"]),
        "knowledge_not_reconstructable": str(ids["p007"]) not in str(dead_document["registry"]),
    }

    restart_manager = PopulationManager()
    restart_founder = restart_manager.create_founder()
    restart_manager.consume(restart_founder, ids["p007"])
    restart_child = restart_manager.spawn(restart_founder)
    restart_manager.kill(restart_founder)
    restart_payload = restart_manager.serialize()
    restored = PopulationManager.restore(restart_payload)
    population_restart = {
        "registry_equal": restored.registry_snapshot() == restart_manager.registry_snapshot(),
        "live_ids_equal": restored.live_ids() == restart_manager.live_ids(),
        "live_states_equal": restored.live_state_digests() == restart_manager.live_state_digests(),
        "survivor_id": restart_child,
    }

    no_automatic_spawn_manager = PopulationManager()
    no_automatic_spawn_manager.create_founder()
    before_consume_count = len(no_automatic_spawn_manager.live_ids())
    no_automatic_spawn_manager.consume("C0", ids["p007"])
    no_automatic_spawn = {
        "count_unchanged_by_consume": len(no_automatic_spawn_manager.live_ids()) == before_consume_count,
        "count": len(no_automatic_spawn_manager.live_ids()),
    }

    return {
        "founder_creation": founder_creation,
        "exact_inheritance": exact_inheritance,
        "independent_divergence": independent_divergence,
        "multi_parent": multi_parent,
        "lineage": lineage,
        "population_cap": population_cap,
        "generation_cap": generation_cap,
        "cell_death": cell_death,
        "founder_death_descendant_survival": cell_death,
        "population_restart": population_restart,
        "knowledge_containment": knowledge_containment,
        "no_automatic_spawn": no_automatic_spawn,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    anchor_errors = []
    if sha256(CELL_PATH) != config.get("cell_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(EXPORT_PATH) != config.get("export_source_sha256"):
        anchor_errors.append("KC-2B export source hash mismatch")
    if sha256(CHILD_PATH) != config.get("child_creation_source_sha256"):
        anchor_errors.append("KC-2D child creation source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    resource = resource_manifest()
    resource_pass = resource == {
        "registry_fields": config["registry_fields"],
        "knowledge_state_in_registry": config["knowledge_state_in_registry"],
        "max_population": config["max_population"],
        "max_generation": config["max_generation"],
        "automatic_spawn_calls": config["automatic_spawn_calls"],
        "external_infrastructure": config["external_infrastructure"],
        "uses_fitness": False,
        "uses_selection": False,
        "uses_mutation_at_birth": False,
    }
    source_audit = audit_manager_source(MANAGER_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "resource_boundary": resource_pass,
        "knowledge_containment_audit": source_audit["status"] == "PASS" and first["knowledge_containment"]["registry_safe"] and first["knowledge_containment"]["registry_has_no_state_fields"],
        "founder": first["founder_creation"]["live_count"] == 1 and first["founder_creation"]["registry_safe"],
        "explicit_spawn": first["exact_inheritance"]["equal_at_birth"],
        "exact_inheritance": first["exact_inheritance"]["equal_at_birth"],
        "independent_divergence": all(first["independent_divergence"].values()),
        "lineage": first["lineage"]["parent_links_present"],
        "multi_parent": first["multi_parent"]["distinct_children"] and first["multi_parent"]["first_child_parent"] == "C0" and first["multi_parent"]["second_parent"] == "C1",
        "population_cap": first["population_cap"]["live_count_before_attempt"] == MAX_POPULATION and first["population_cap"]["failed_closed"] and first["population_cap"]["unchanged"],
        "generation_cap": first["generation_cap"]["max_generation"] == MAX_GENERATION and first["generation_cap"]["failed_closed"],
        "cell_death": first["cell_death"]["survivor_alive"] and first["cell_death"]["survivor_unchanged"],
        "founder_death": first["founder_death_descendant_survival"]["founder_dead"] and first["founder_death_descendant_survival"]["survivor_alive"],
        "population_restart": all(first["population_restart"].values()) if isinstance(first["population_restart"], dict) else False,
        "knowledge_disappears_with_last_cell": all(first["knowledge_containment"].values()),
        "no_automatic_spawn": first["no_automatic_spawn"]["count_unchanged_by_consume"],
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3A-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3A_DEV_COMPLETE" if passed else "KC_3A_DEV_INVALID",
        "cell_source_sha256": sha256(CELL_PATH),
        "export_source_sha256": sha256(EXPORT_PATH),
        "child_creation_source_sha256": sha256(CHILD_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "manager_source_sha256": sha256(MANAGER_PATH),
        "anchor_errors": anchor_errors,
        "resource_manifest": resource,
        "manager_source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development bounded population lifecycle characterization only; fitness, selection, mutation-at-birth, autonomous reproduction, and scientific conclusions are forbidden.",
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
