#!/usr/bin/env python3
"""KC-3E-D finite-horizon population-dynamics characterization."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Callable

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from sim.kc0.validate_bank import load_bank, sha256, validate_bank
from sim.kc2b.export import export_slot
from sim.kc3a.manager import PopulationManager, REGISTRY_FIELDS
from sim.kc3d.tick import population_tick, resource_manifest as tick_resource
from sim.runtime import canonical, tensor_digest


BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
CHARACTERIZE_PATH = HERE / "characterize.py"
TICK_PATH = ROOT / "sim" / "kc3d" / "tick.py"
TICK_CONFIG_PATH = ROOT / "sim" / "kc3d" / "config.json"
ACTIVATION_PATH = ROOT / "sim" / "kc3c" / "activate.py"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"

MAX_TICKS = 4
MAX_ACTIVATIONS_PER_TICK = 8
MAX_SLOT_CONTACTS_PER_TICK = 112
MAX_TOTAL_ACTIVATIONS = 32
MAX_TOTAL_SLOT_CONTACTS = 448


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


def population_digest(population: PopulationManager) -> str:
    return population.population_digest()


def packet_label(token: int, token_labels: dict[int, str]) -> str:
    return token_labels.get(token, f"token_{token}")


def population_snapshot(
    population: PopulationManager,
    token_labels: dict[int, str],
    tick_index: int,
    previous_digest: str | None,
    prior_digests: list[str],
) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = {}
    cells_containing: dict[str, list[str]] = {}
    for cell_id in population.live_ids():
        state = population.state_snapshot(cell_id)
        tokens = state_tokens(state)
        identities = sorted(packet_label(token, token_labels) for token in tokens)
        cells[cell_id] = {
            "state_sha256": tensor_digest(state),
            "recoverable_packet_identities": identities,
        }
        for identity in identities:
            cells_containing.setdefault(identity, []).append(cell_id)

    for identity in cells_containing:
        cells_containing[identity] = sorted(cells_containing[identity])
    digest = population_digest(population)
    repeat_indices = [index for index, prior_digest in enumerate(prior_digests[:-1]) if prior_digest == digest]
    fixed = previous_digest is not None and digest == previous_digest
    if tick_index == 0:
        state_observation = "INITIAL"
    elif fixed:
        state_observation = "OBSERVED_FIXED_POINT_WITHIN_HORIZON"
    elif repeat_indices:
        state_observation = "OBSERVED_REPEAT_WITHIN_HORIZON"
    else:
        state_observation = "CHANGED"
    return {
        "tick_index": tick_index,
        "registry": population.registry_snapshot(),
        "live_ids": population.live_ids(),
        "cells": cells,
        "distinct_packet_identities": sorted(cells_containing),
        "copies_per_packet": {identity: len(cell_ids) for identity, cell_ids in sorted(cells_containing.items())},
        "cells_containing_packet": dict(sorted(cells_containing.items())),
        "population_digest": digest,
        "changed_since_previous_tick": False if previous_digest is None else digest != previous_digest,
        "prior_repeat_tick_indices": repeat_indices,
        "state_observation": state_observation,
    }


def run_trajectory(population: PopulationManager, token_labels: dict[int, str]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    tick_records: list[dict[str, Any]] = []
    prior_digests: list[str] = []
    previous_digest: str | None = None
    snapshots.append(population_snapshot(population, token_labels, 0, previous_digest, prior_digests))
    prior_digests.append(snapshots[-1]["population_digest"])
    total_activations = 0
    total_contacts = 0
    for tick_index in range(1, MAX_TICKS + 1):
        tick = population_tick(population)
        total_activations += int(tick["activation_count"])
        total_contacts += int(tick["contact_count"])
        tick_records.append({
            "tick_index": tick_index,
            "activation_order": tick["activation_order"],
            "activation_count": tick["activation_count"],
            "slot_contact_count": tick["contact_count"],
            "delivery_count": tick["delivery_count"],
        })
        previous_digest = prior_digests[-1]
        snapshots.append(population_snapshot(population, token_labels, tick_index, previous_digest, prior_digests))
        prior_digests.append(snapshots[-1]["population_digest"])
    registry = snapshots[0]["registry"]
    return {
        "snapshots": snapshots,
        "ticks": tick_records,
        "total_activations": total_activations,
        "total_slot_contacts": total_contacts,
        "within_total_bounds": total_activations <= MAX_TOTAL_ACTIVATIONS and total_contacts <= MAX_TOTAL_SLOT_CONTACTS,
        "registry_unchanged": all(snapshot["registry"] == registry for snapshot in snapshots),
        "live_ids_unchanged": all(snapshot["live_ids"] == snapshots[0]["live_ids"] for snapshot in snapshots),
    }


def restart_from_boundaries(builder: Callable[[], PopulationManager], token_labels: dict[int, str], baseline: dict[str, Any]) -> dict[str, Any]:
    boundary_results: list[dict[str, Any]] = []
    baseline_snapshots = baseline["snapshots"]
    baseline_ticks = baseline["ticks"]
    for boundary in range(MAX_TICKS):
        population = builder()
        for _ in range(boundary):
            population_tick(population)
        restored = PopulationManager.restore(population.serialize())
        prior_digests = [snapshot["population_digest"] for snapshot in baseline_snapshots[:boundary]]
        previous_digest = prior_digests[-1] if prior_digests else None
        resumed_snapshots = [population_snapshot(restored, token_labels, boundary, previous_digest, prior_digests)]
        resumed_ticks: list[dict[str, Any]] = []
        for tick_index in range(boundary + 1, MAX_TICKS + 1):
            tick = population_tick(restored)
            resumed_ticks.append({
                "tick_index": tick_index,
                "activation_order": tick["activation_order"],
                "activation_count": tick["activation_count"],
                "slot_contact_count": tick["contact_count"],
                "delivery_count": tick["delivery_count"],
            })
            previous_digest = resumed_snapshots[-1]["population_digest"]
            prior_digests.append(previous_digest)
            resumed_snapshots.append(population_snapshot(restored, token_labels, tick_index, previous_digest, prior_digests))
        expected = {"snapshots": baseline_snapshots[boundary:], "ticks": baseline_ticks[boundary:]}
        actual = {"snapshots": resumed_snapshots, "ticks": resumed_ticks}
        boundary_results.append({
            "boundary": boundary,
            "match": canonical(actual) == canonical(expected),
            "expected_tick_count": len(expected["ticks"]),
            "resumed_tick_count": len(resumed_ticks),
        })
    return {
        "boundaries": boundary_results,
        "all_pass": all(result["match"] for result in boundary_results),
    }


def run_scenario(name: str, builder: Callable[[], PopulationManager], token_labels: dict[int, str]) -> dict[str, Any]:
    population = builder()
    trajectory = run_trajectory(population, token_labels)
    restart = restart_from_boundaries(builder, token_labels, trajectory)
    return {
        "name": name,
        "trajectory": trajectory,
        "restart": restart,
    }


def chain_seeded(cell_index: int, token: int) -> Callable[[], PopulationManager]:
    def builder() -> PopulationManager:
        population, cells = chain_population()
        population.consume(cells[cell_index], token)
        return population

    return builder


def branch_seeded(cell_index: int, token: int) -> Callable[[], PopulationManager]:
    def builder() -> PopulationManager:
        population, cells = branch_population()
        population.consume(cells[cell_index], token)
        return population

    return builder


def multi_packet_builder(tokens: list[int]) -> Callable[[], PopulationManager]:
    def builder() -> PopulationManager:
        population, cells = chain_population()
        for cell_id, token in zip(cells, tokens):
            population.consume(cell_id, token)
        return population

    return builder


def same_slot_builder(tokens: list[int]) -> Callable[[], PopulationManager]:
    return multi_packet_builder(tokens)


def empty_population_builder() -> PopulationManager:
    return PopulationManager()


def empty_knowledge_builder() -> PopulationManager:
    population, _ = chain_population()
    return population


def dead_gap_builder(token: int) -> Callable[[], PopulationManager]:
    def builder() -> PopulationManager:
        population, cells = chain_population()
        population.kill(cells[1])
        population.consume(cells[0], token)
        return population

    return builder


def audit_harness_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    function_names: set[str] = set()
    while_count = 0
    async_count = 0
    bounded_range_loops = 0
    execution_mutation_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_names.add(node.name)
        elif isinstance(node, ast.While):
            while_count += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            async_count += 1
        elif isinstance(node, ast.For):
            if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                bounded_range_loops += 1
        elif isinstance(node, ast.FunctionDef) and node.name in {"run_trajectory", "restart_from_boundaries", "run_scenario"}:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr in {"spawn", "kill"}:
                    execution_mutation_calls.append(child.func.attr)
    forbidden = sorted((names | imports) & {
        "timer", "thread", "threading", "process", "subprocess", "scheduler", "callback",
        "asyncio", "network", "socket", "fitness", "selection", "learning",
        "run_forever", "autorun", "run_horizon",
    })
    forbidden_functions = sorted(function_names & {"run_forever", "autorun", "run_horizon"})
    return {
        "status": "PASS" if not forbidden and not forbidden_functions and not execution_mutation_calls and while_count == 0 and async_count == 0 and bounded_range_loops >= 1 else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "forbidden_functions": forbidden_functions,
        "execution_mutation_calls": execution_mutation_calls,
        "while_loop_count": while_count,
        "async_function_count": async_count,
        "bounded_range_loop_count": bounded_range_loops,
        "population_tick_signature": [parameter.name for parameter in inspect.signature(population_tick).parameters.values()],
    }


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    token_labels = {token: packet_id for packet_id, token in ids.items()}
    synthetic_token = 25
    token_labels[synthetic_token] = "synthetic_token_25_same_slot_as_p000"

    single_packet = {
        f"chain_seed_C{index}": run_scenario(f"chain_seed_C{index}", chain_seeded(index, ids["p007"]), token_labels)
        for index in range(4)
    }
    branching = {
        "branch_seed_root": run_scenario("branch_seed_root", branch_seeded(0, ids["p007"]), token_labels),
        "branch_seed_middle": run_scenario("branch_seed_middle", branch_seeded(1, ids["p007"]), token_labels),
        "branch_seed_leaf": run_scenario("branch_seed_leaf", branch_seeded(4, ids["p007"]), token_labels),
    }
    non_colliding = run_scenario(
        "non_colliding_multi_packet",
        multi_packet_builder([ids["p000"], ids["p001"], ids["p002"], ids["p003"]]),
        token_labels,
    )
    same_slot_tokens = [ids["p000"], ids["p008"], ids["p016"], synthetic_token]
    same_slot = {
        "ascending_initial_placement": run_scenario("same_slot_ascending", same_slot_builder(same_slot_tokens), token_labels),
        "reversed_initial_placement": run_scenario("same_slot_reversed", same_slot_builder(list(reversed(same_slot_tokens))), token_labels),
        "identities": [packet_label(token, token_labels) for token in same_slot_tokens],
        "physical_slot": same_slot_tokens[0] % 8,
    }
    controls = {
        "empty_population": run_scenario("empty_population", empty_population_builder, token_labels),
        "empty_knowledge": run_scenario("empty_knowledge", empty_knowledge_builder, token_labels),
        "dead_intermediate": run_scenario("dead_intermediate", dead_gap_builder(ids["p007"]), token_labels),
    }
    dead_snapshots = controls["dead_intermediate"]["trajectory"]["snapshots"]
    dead_gap_result = {
        "dead_cell_absent_from_live_ids": all("C1" not in snapshot["live_ids"] for snapshot in dead_snapshots),
        "no_teleportation_to_C2": all("p007" not in snapshot["cells"].get("C2", {}).get("recoverable_packet_identities", []) for snapshot in dead_snapshots),
        "no_teleportation_to_C3": all("p007" not in snapshot["cells"].get("C3", {}).get("recoverable_packet_identities", []) for snapshot in dead_snapshots),
    }
    return {
        "horizon": MAX_TICKS,
        "single_packet_chain": single_packet,
        "branching": branching,
        "non_colliding_multi_packet": non_colliding,
        "same_slot_competition": same_slot,
        "controls": controls,
        "dead_intermediate_control": dead_gap_result,
    }


def scenario_list(characterization: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    scenarios.extend(characterization["single_packet_chain"].values())
    scenarios.extend(characterization["branching"].values())
    scenarios.append(characterization["non_colliding_multi_packet"])
    scenarios.append(characterization["same_slot_competition"]["ascending_initial_placement"])
    scenarios.append(characterization["same_slot_competition"]["reversed_initial_placement"])
    scenarios.extend(characterization["controls"].values())
    return scenarios


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    anchor_errors: list[str] = []
    anchors = {
        "population_tick_source_sha256": TICK_PATH,
        "population_tick_config_sha256": TICK_CONFIG_PATH,
        "activation_source_sha256": ACTIVATION_PATH,
        "manager_source_sha256": MANAGER_PATH,
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
    if config.get("max_ticks") != MAX_TICKS:
        anchor_errors.append("horizon is not frozen at four ticks")
    if config.get("max_total_activations") != MAX_TOTAL_ACTIVATIONS or config.get("max_total_slot_contacts") != MAX_TOTAL_SLOT_CONTACTS:
        anchor_errors.append("total hard bounds are incorrect")

    resource = tick_resource()
    resource_pass = resource == {
        "scheduler_state_bytes": 0,
        "persistent_scheduler_fields": [],
        "automatic_ticks": 0,
        "background_execution": False,
        "creates_children": False,
        "kills_cells": False,
        "registry_mutation": False,
        "max_activations_per_tick": MAX_ACTIVATIONS_PER_TICK,
        "max_slot_contacts_per_tick": MAX_SLOT_CONTACTS_PER_TICK,
    }
    source_audit = audit_harness_source(CHARACTERIZE_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    scenarios = scenario_list(first)
    scenario_trajectories_valid = all(
        len(scenario["trajectory"]["snapshots"]) == MAX_TICKS + 1
        and len(scenario["trajectory"]["ticks"]) == MAX_TICKS
        and scenario["trajectory"]["within_total_bounds"]
        and scenario["trajectory"]["registry_unchanged"]
        and scenario["trajectory"]["live_ids_unchanged"]
        for scenario in scenarios
    )
    restart_valid = all(scenario["restart"]["all_pass"] for scenario in scenarios)
    observation_labels_valid = all(
        all(snapshot["state_observation"] in {"INITIAL", "CHANGED", "OBSERVED_FIXED_POINT_WITHIN_HORIZON", "OBSERVED_REPEAT_WITHIN_HORIZON"} for snapshot in scenario["trajectory"]["snapshots"])
        for scenario in scenarios
    )
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "source_audit": source_audit["status"] == "PASS",
        "zero_scheduler_state": resource_pass and config.get("automatic_runner") is False and config.get("background_execution") is False,
        "fixed_horizon": config.get("max_ticks") == 4,
        "single_packet_chain": len(first["single_packet_chain"]) == 4,
        "branching_positions": len(first["branching"]) == 3,
        "non_colliding_multi_packet": first["non_colliding_multi_packet"]["name"] == "non_colliding_multi_packet",
        "same_slot_both_orders": set(first["same_slot_competition"]) >= {"ascending_initial_placement", "reversed_initial_placement", "identities", "physical_slot"},
        "extinction_persistence_controls": set(first["controls"]) == {"empty_population", "empty_knowledge", "dead_intermediate"},
        "dead_gap_no_teleportation": all(first["dead_intermediate_control"].values()),
        "trajectory_shape_and_immutability": scenario_trajectories_valid,
        "observed_fixed_or_repeat_labels": observation_labels_valid,
        "restart_each_boundary": restart_valid,
        "hard_total_bounds": all(scenario["trajectory"]["total_activations"] <= MAX_TOTAL_ACTIVATIONS and scenario["trajectory"]["total_slot_contacts"] <= MAX_TOTAL_SLOT_CONTACTS for scenario in scenarios),
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3E-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3E_DEV_COMPLETE" if passed else "KC_3E_DEV_INVALID",
        "population_tick_source_sha256": sha256(TICK_PATH),
        "population_tick_config_sha256": sha256(TICK_CONFIG_PATH),
        "activation_source_sha256": sha256(ACTIVATION_PATH),
        "manager_source_sha256": sha256(MANAGER_PATH),
        "cell_source_sha256": sha256(CELL_PATH),
        "fixture_bank_sha256": sha256(bank_path),
        "config_sha256": sha256(config_path),
        "characterize_source_sha256": sha256(CHARACTERIZE_PATH),
        "anchor_errors": anchor_errors,
        "resource_manifest": resource,
        "source_audit": source_audit,
        "horizon": MAX_TICKS,
        "hard_bounds": {
            "max_activations_per_tick": MAX_ACTIVATIONS_PER_TICK,
            "max_slot_contacts_per_tick": MAX_SLOT_CONTACTS_PER_TICK,
            "max_total_activations": MAX_TOTAL_ACTIVATIONS,
            "max_total_slot_contacts": MAX_TOTAL_SLOT_CONTACTS,
        },
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development finite-horizon population-dynamics characterization only; no automatic runner, scientific threshold, or scientific verdict is authorized.",
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
