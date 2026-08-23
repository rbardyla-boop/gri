#!/usr/bin/env python3
"""KC-3D-D bounded population tick characterization."""
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

from sim.kc0.validate_bank import load_bank, sha256, validate_bank
from sim.kc2b.export import export_slot
from sim.kc3a.manager import MAX_POPULATION, PopulationManager, REGISTRY_FIELDS
from sim.kc3c.activate import resource_manifest as activation_resource
from sim.kc3d.tick import MAX_ACTIVATIONS_PER_TICK, MAX_SLOT_CONTACTS_PER_TICK, population_tick, resource_manifest
from sim.runtime import canonical, tensor_digest


BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
TICK_PATH = HERE / "tick.py"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
SHARE_PATH = ROOT / "sim" / "kc3b" / "share.py"
ACTIVATION_PATH = ROOT / "sim" / "kc3c" / "activate.py"
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
    tail = population.spawn(right)
    return population, [founder, first, left, right, tail]


def full_population() -> tuple[PopulationManager, list[str]]:
    population = PopulationManager()
    founder = population.create_founder()
    first = population.spawn(founder)
    left = population.spawn(first)
    right = population.spawn(first)
    left_a = population.spawn(left)
    left_b = population.spawn(left)
    right_a = population.spawn(right)
    right_b = population.spawn(right)
    return population, [founder, first, left, right, left_a, left_b, right_a, right_b]


def audit_tick_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    classes = 0
    global_statements = 0
    tick_parameters: list[str] | None = None
    activate_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
            if isinstance(node.ctx, ast.Load) and node.id == "activate_cell":
                activate_calls += 1
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
        elif isinstance(node, ast.FunctionDef) and node.name == "population_tick":
            tick_parameters = [argument.arg for argument in node.args.args]
    forbidden = sorted((names | imports) & {
        "packet_id", "token_id", "target_id", "query_id", "history", "queue", "cursor",
        "sent_set", "routing", "fitness", "selection", "network", "socket", "thread",
        "process", "subprocess", "timer", "scheduler", "spawn", "kill",
    })
    runtime_signature = [parameter.name for parameter in inspect.signature(population_tick).parameters.values()]
    expected_signature = ["population"]
    signature_ok = runtime_signature == expected_signature and tick_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok and activate_calls == 1 else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": runtime_signature,
        "source_signature": tick_parameters,
        "signature_ok": signature_ok,
        "direct_activate_cell_calls": activate_calls,
    }


def fill_all_slots(population: PopulationManager, cell_ids: list[str], tokens: list[int]) -> None:
    for cell_id in cell_ids:
        for token in tokens:
            population.consume(cell_id, token)


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    packet = ids["p007"]
    second_packet = ids["p000"]
    conflict = ids["p015"]
    full_tokens = [ids[f"p00{i}"] for i in range(8)]

    forward, forward_cells = chain_population()
    forward_source = forward_cells[0]
    start_live_ids = forward.live_ids()
    forward.consume(forward_source, packet)
    forward_tick = population_tick(forward)
    forward_result = {
        "all_cells_receive": all(packet in state_tokens(forward.state_snapshot(cell_id)) for cell_id in forward_cells),
        "activation_order": forward_tick["activation_order"] == start_live_ids,
        "secondary_forwarding": packet in state_tokens(forward.state_snapshot(forward_cells[-1])),
    }
    exactly_once = {
        "count_matches_schedule": forward_tick["activation_count"] == len(start_live_ids),
        "unique_sources": len({entry["source_id"] for entry in forward_tick["activations"]}) == len(start_live_ids),
        "one_record_per_source": [entry["source_id"] for entry in forward_tick["activations"]] == start_live_ids,
    }

    reverse, reverse_cells = chain_population()
    reverse_source = reverse_cells[-1]
    reverse.consume(reverse_source, packet)
    reverse_ticks: list[dict[str, object]] = []
    reverse_states: list[list[list[int]]] = []
    for _ in range(3):
        reverse_ticks.append(population_tick(reverse))
        reverse_states.append([state_tokens(reverse.state_snapshot(cell_id)) for cell_id in reverse_cells])
    reverse_result = {
        "tick_one_reaches_previous_cell": packet in reverse_states[0][2] and packet not in reverse_states[0][1],
        "tick_two_reaches_next_previous_cell": packet in reverse_states[1][1] and packet not in reverse_states[1][0],
        "tick_three_reaches_founder": packet in reverse_states[2][0],
        "three_explicit_ticks": len(reverse_ticks) == 3,
    }

    branch, branch_cells = branch_population()
    branch_source = branch_cells[0]
    branch.consume(branch_source, packet)
    branch_tick = population_tick(branch)
    branching_result = {
        "all_live_cells_receive": all(packet in state_tokens(branch.state_snapshot(cell_id)) for cell_id in branch_cells),
        "canonical_order": branch_tick["activation_order"] == branch.live_ids(),
        "secondary_child_forwarded": packet in state_tokens(branch.state_snapshot(branch_cells[-1])),
        "activation_count": branch_tick["activation_count"] == len(branch_cells),
    }

    multi, multi_cells = chain_population()
    multi.consume(multi_cells[0], packet)
    multi.consume(multi_cells[0], second_packet)
    multi_tick = population_tick(multi)
    multi_result = {
        "source_has_both": sorted(state_tokens(multi.state_snapshot(multi_cells[0]))) == sorted([packet, second_packet]),
        "tail_has_both": sorted(state_tokens(multi.state_snapshot(multi_cells[-1]))) == sorted([packet, second_packet]),
        "tick_completed": multi_tick["activation_count"] == len(multi_cells),
    }

    dead, dead_cells = branch_population()
    dead.kill(dead_cells[2])
    dead.consume(dead_cells[0], packet)
    dead_before_registry = dead.registry_snapshot()
    dead_tick = population_tick(dead)
    dead_result = {
        "dead_excluded": dead_cells[2] not in dead_tick["activation_order"],
        "live_cells_each_once": dead_tick["activation_order"] == dead.live_ids(),
        "knowledge_reaches_live_branch": packet in state_tokens(dead.state_snapshot(dead_cells[3])) and packet in state_tokens(dead.state_snapshot(dead_cells[4])),
        "dead_not_resurrected": dead_cells[2] not in dead.live_ids(),
        "registry_unchanged": dead.registry_snapshot() == dead_before_registry,
    }

    collision, collision_cells = branch_population()
    collision.consume(collision_cells[0], packet)
    collision.consume(collision_cells[2], conflict)
    collision_tick = population_tick(collision)
    collision_result = {
        "canonical_contact_order": collision_tick["activation_order"] == collision.live_ids(),
        "ancestor_value_wins_deterministically": packet in state_tokens(collision.state_snapshot(collision_cells[1])) and conflict not in state_tokens(collision.state_snapshot(collision_cells[1])),
        "descendant_was_overwritten_before_turn": packet in state_tokens(collision.state_snapshot(collision_cells[2])) and conflict not in state_tokens(collision.state_snapshot(collision_cells[2])),
    }

    stable, stable_cells = chain_population()
    stable.consume(stable_cells[0], packet)
    population_tick(stable)
    stable_before_repeat = population_snapshot(stable)
    stable_repeat_tick = population_tick(stable)
    no_conflict_repeat = {
        "state_stable": population_snapshot(stable) == stable_before_repeat,
        "same_schedule": stable_repeat_tick["activation_order"] == stable_cells,
    }

    restarted, restarted_cells = chain_population()
    restarted.consume(restarted_cells[-1], packet)
    uninterrupted = [population_tick(restarted) for _ in range(3)]
    interrupted, interrupted_cells = chain_population()
    interrupted.consume(interrupted_cells[-1], packet)
    interrupted_first = population_tick(interrupted)
    restored = PopulationManager.restore(interrupted.serialize())
    interrupted_rest = [population_tick(restored) for _ in range(2)]
    between_tick_restart = {
        "first_tick_schedule_equal": interrupted_first["activation_order"] == uninterrupted[0]["activation_order"],
        "final_state_equal": restored.live_state_digests() == restarted.live_state_digests(),
        "registry_equal": restored.registry_snapshot() == restarted.registry_snapshot(),
        "live_ids_equal": restored.live_ids() == restarted.live_ids(),
        "replayed_tick_count": len(interrupted_rest) == 2,
    }

    malformed, malformed_cells = chain_population()
    malformed.consume(malformed_cells[0], packet)
    malformed_cell, malformed_state = malformed._cells[malformed_cells[1]]
    broken_state = malformed_state.detach().clone()
    broken_state[0, 8] = 2
    malformed._cells[malformed_cells[1]] = (malformed_cell, broken_state)
    malformed_before = population_snapshot(malformed)
    malformed_rejected = False
    try:
        population_tick(malformed)
    except ValueError:
        malformed_rejected = True
    malformed_preflight = {
        "rejected": malformed_rejected,
        "no_mutation_before_failure": population_snapshot(malformed) == malformed_before,
    }

    immutable, immutable_cells = chain_population()
    immutable.consume(immutable_cells[0], packet)
    immutable_before = population_snapshot(immutable)
    immutable_tick = population_tick(immutable)
    immutable_after = population_snapshot(immutable)
    registry_immutability = {
        "registry_unchanged": immutable_after["registry"] == immutable_before["registry"],
        "generation_unchanged": [row["generation"] for row in immutable_after["registry"]] == [row["generation"] for row in immutable_before["registry"]],
        "live_population_unchanged": immutable_after["live_ids"] == immutable_before["live_ids"],
        "tick_had_no_creation_or_death": immutable_tick["activation_count"] == len(immutable_cells),
    }

    budget, budget_cells = full_population()
    fill_all_slots(budget, budget_cells, full_tokens)
    budget_tick = population_tick(budget)
    hard_budget = {
        "activation_bound": budget_tick["activation_count"] <= MAX_ACTIVATIONS_PER_TICK,
        "contact_bound": budget_tick["contact_count"] <= MAX_SLOT_CONTACTS_PER_TICK,
        "maximum_case_reached": budget_tick["activation_count"] == 8 and budget_tick["contact_count"] == 112,
    }

    empty = PopulationManager()
    empty_before = population_snapshot(empty)
    empty_tick = population_tick(empty)
    empty_population = {
        "zero_activations": empty_tick["activation_count"] == 0,
        "zero_contacts": empty_tick["contact_count"] == 0,
        "unchanged": population_snapshot(empty) == empty_before,
    }

    return {
        "forward_cascade": forward_result,
        "exactly_once": exactly_once,
        "reverse_cascade": reverse_result,
        "branching": branching_result,
        "multi_packet": multi_result,
        "dead_cells": dead_result,
        "collision_order": collision_result,
        "no_conflict_repeat": no_conflict_repeat,
        "between_tick_restart": between_tick_restart,
        "malformed_state_preflight": malformed_preflight,
        "registry_immutability": registry_immutability,
        "hard_budget": hard_budget,
        "empty_population": empty_population,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    anchor_errors: list[str] = []
    anchors = {
        "manager_source_sha256": MANAGER_PATH,
        "share_source_sha256": SHARE_PATH,
        "activation_source_sha256": ACTIVATION_PATH,
        "cell_source_sha256": CELL_PATH,
        "fixture_bank_sha256": bank_path,
    }
    for field, path in anchors.items():
        if sha256(path) != config.get(field):
            anchor_errors.append(f"{field} mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    resource = resource_manifest()
    resource_pass = resource == {
        "scheduler_state_bytes": config["scheduler_state_bytes"],
        "persistent_scheduler_fields": config["persistent_scheduler_fields"],
        "automatic_ticks": config["automatic_ticks"],
        "background_execution": config["background_execution"],
        "creates_children": config["creates_children"],
        "kills_cells": config["kills_cells"],
        "registry_mutation": config["registry_mutation"],
        "max_activations_per_tick": config["max_activations_per_tick"],
        "max_slot_contacts_per_tick": config["max_slot_contacts_per_tick"],
    }
    source_audit = audit_tick_source(TICK_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "source_signature_audit": source_audit["status"] == "PASS",
        "zero_scheduler_state": resource_pass,
        "empty_population": all(first["empty_population"].values()),
        "exactly_once": all(first["exactly_once"].values()),
        "canonical_order": first["forward_cascade"]["activation_order"] and first["branching"]["canonical_order"],
        "forward_cascade": all(first["forward_cascade"].values()),
        "reverse_cascade": all(first["reverse_cascade"].values()),
        "branching": all(first["branching"].values()),
        "multi_packet": all(first["multi_packet"].values()),
        "dead_cells": all(first["dead_cells"].values()),
        "collision_order": all(first["collision_order"].values()),
        "no_conflict_repeat": all(first["no_conflict_repeat"].values()),
        "between_tick_restart": all(first["between_tick_restart"].values()),
        "malformed_state_preflight": all(first["malformed_state_preflight"].values()),
        "registry_immutability": all(first["registry_immutability"].values()),
        "hard_budget": all(first["hard_budget"].values()),
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3D-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3D_DEV_COMPLETE" if passed else "KC_3D_DEV_INVALID",
        "manager_source_sha256": sha256(MANAGER_PATH),
        "share_source_sha256": sha256(SHARE_PATH),
        "activation_source_sha256": sha256(ACTIVATION_PATH),
        "cell_source_sha256": sha256(CELL_PATH),
        "fixture_bank_sha256": sha256(bank_path),
        "config_sha256": sha256(config_path),
        "tick_source_sha256": sha256(TICK_PATH),
        "anchor_errors": anchor_errors,
        "resource_manifest": resource,
        "activation_resource_manifest": activation_resource(),
        "tick_source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "hard_bounds": {
            "max_activations_per_tick": MAX_ACTIVATIONS_PER_TICK,
            "max_slot_contacts_per_tick": MAX_SLOT_CONTACTS_PER_TICK,
        },
        "note": "Development bounded population-tick characterization only; no automatic loop, population dynamics, or scientific conclusion is authorized.",
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
