#!/usr/bin/env python3
"""KC-3F-D scheduler-counterfactual characterization."""
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
from sim.kc3c.activate import activate_cell
from sim.kc3d.tick import population_tick
from sim.kc3e.characterize import branch_population, chain_population, packet_label, population_snapshot
from sim.runtime import canonical


BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
CHARACTERIZE_PATH = HERE / "characterize.py"
TICK_PATH = ROOT / "sim" / "kc3d" / "tick.py"
TICK_CONFIG_PATH = ROOT / "sim" / "kc3d" / "config.json"
KC3E_CHARACTERIZE_PATH = ROOT / "sim" / "kc3e" / "characterize.py"
ACTIVATION_PATH = ROOT / "sim" / "kc3c" / "activate.py"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"

ORDER_NAMES = ("ascending", "descending", "even_odd", "odd_even")
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


def _canonical_live_ids(population: PopulationManager) -> list[str]:
    records = population.registry_snapshot()
    live_ids: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if set(record) != set(REGISTRY_FIELDS):
            raise ValueError("lifecycle metadata is invalid")
        cell_id = record["cell_id"]
        if cell_id != f"C{index}" or cell_id in seen or not isinstance(record["alive"], bool):
            raise ValueError("lifecycle registry is invalid")
        seen.add(cell_id)
        if record["alive"]:
            live_ids.append(cell_id)
    if len(live_ids) > MAX_ACTIVATIONS_PER_TICK:
        raise ValueError("live population exceeds counterfactual tick bound")
    return live_ids


def _ordered_live_ids(population: PopulationManager, order_name: str) -> list[str]:
    live_ids = _canonical_live_ids(population)
    numeric = lambda cell_id: int(cell_id[1:])
    ascending = sorted(live_ids, key=numeric)
    if order_name == "ascending":
        return ascending
    if order_name == "descending":
        return list(reversed(ascending))
    even = [cell_id for cell_id in ascending if numeric(cell_id) % 2 == 0]
    odd = [cell_id for cell_id in ascending if numeric(cell_id) % 2 == 1]
    if order_name == "even_odd":
        return even + odd
    if order_name == "odd_even":
        return odd + even
    raise ValueError("order is not preregistered")


def _prevalidate_states(population: PopulationManager, order: list[str]) -> None:
    for cell_id in order:
        state = population.state_snapshot(cell_id)
        for slot_id in range(8):
            export_slot(state, slot_id)


def counterfactual_tick(population: PopulationManager, order_name: str) -> dict[str, object]:
    """Run one fixed-order tick in the characterization layer only."""
    order = _ordered_live_ids(population, order_name)
    _prevalidate_states(population, order)
    activations: list[dict[str, object]] = []
    contact_count = 0
    delivery_count = 0
    for cell_id in order:
        activation = activate_cell(population, cell_id)
        activations.append(activation)
        contact_count += int(activation["contact_count"])
        delivery_count += int(activation["delivery_count"])
    if contact_count > MAX_SLOT_CONTACTS_PER_TICK:
        raise RuntimeError("counterfactual tick exceeded contact bound")
    return {
        "order_name": order_name,
        "activation_order": order,
        "live_ids_at_tick_start": list(order),
        "activation_count": len(activations),
        "contact_count": contact_count,
        "delivery_count": delivery_count,
        "activations": activations,
    }


def _trajectory_snapshot(population: PopulationManager, labels: dict[int, str], tick_index: int, previous_digest: str | None, prior_digests: list[str]) -> dict[str, Any]:
    return population_snapshot(population, labels, tick_index, previous_digest, prior_digests)


def run_trajectory(population: PopulationManager, runner: Callable[[PopulationManager], dict[str, object]], labels: dict[int, str]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    ticks: list[dict[str, Any]] = []
    prior_digests: list[str] = []
    previous_digest: str | None = None
    snapshots.append(_trajectory_snapshot(population, labels, 0, previous_digest, prior_digests))
    prior_digests.append(snapshots[-1]["population_digest"])
    total_activations = 0
    total_contacts = 0
    for tick_index in range(1, MAX_TICKS + 1):
        tick = runner(population)
        total_activations += int(tick["activation_count"])
        total_contacts += int(tick["contact_count"])
        ticks.append({
            "tick_index": tick_index,
            "activation_order": tick["activation_order"],
            "activation_count": tick["activation_count"],
            "slot_contact_count": tick["contact_count"],
            "delivery_count": tick["delivery_count"],
        })
        previous_digest = prior_digests[-1]
        snapshots.append(_trajectory_snapshot(population, labels, tick_index, previous_digest, prior_digests))
        prior_digests.append(snapshots[-1]["population_digest"])
    registry = snapshots[0]["registry"]
    return {
        "snapshots": snapshots,
        "ticks": ticks,
        "total_activations": total_activations,
        "total_slot_contacts": total_contacts,
        "within_total_bounds": total_activations <= MAX_TOTAL_ACTIVATIONS and total_contacts <= MAX_TOTAL_SLOT_CONTACTS,
        "registry_unchanged": all(snapshot["registry"] == registry for snapshot in snapshots),
        "live_ids_unchanged": all(snapshot["live_ids"] == snapshots[0]["live_ids"] for snapshot in snapshots),
    }


def restart_from_boundaries(builder: Callable[[], PopulationManager], runner_factory: Callable[[], Callable[[PopulationManager], dict[str, object]]], labels: dict[int, str], baseline: dict[str, Any]) -> dict[str, Any]:
    boundary_results: list[dict[str, Any]] = []
    baseline_snapshots = baseline["snapshots"]
    baseline_ticks = baseline["ticks"]
    for boundary in range(MAX_TICKS):
        population = builder()
        runner = runner_factory()
        for _ in range(boundary):
            runner(population)
        restored = PopulationManager.restore(population.serialize())
        prior_digests = [snapshot["population_digest"] for snapshot in baseline_snapshots[:boundary]]
        previous_digest = prior_digests[-1] if prior_digests else None
        resumed_snapshots = [_trajectory_snapshot(restored, labels, boundary, previous_digest, prior_digests)]
        resumed_ticks: list[dict[str, Any]] = []
        for tick_index in range(boundary + 1, MAX_TICKS + 1):
            tick = runner(restored)
            resumed_ticks.append({
                "tick_index": tick_index,
                "activation_order": tick["activation_order"],
                "activation_count": tick["activation_count"],
                "slot_contact_count": tick["contact_count"],
                "delivery_count": tick["delivery_count"],
            })
            previous_digest = resumed_snapshots[-1]["population_digest"]
            prior_digests.append(previous_digest)
            resumed_snapshots.append(_trajectory_snapshot(restored, labels, tick_index, previous_digest, prior_digests))
        expected = {"snapshots": baseline_snapshots[boundary:], "ticks": baseline_ticks[boundary:]}
        actual = {"snapshots": resumed_snapshots, "ticks": resumed_ticks}
        boundary_results.append({
            "boundary": boundary,
            "match": canonical(actual) == canonical(expected),
            "expected_tick_count": len(expected["ticks"]),
            "resumed_tick_count": len(resumed_ticks),
        })
    return {"boundaries": boundary_results, "all_pass": all(result["match"] for result in boundary_results)}


def run_condition(name: str, builder: Callable[[], PopulationManager], runner_factory: Callable[[], Callable[[PopulationManager], dict[str, object]]], labels: dict[int, str]) -> dict[str, Any]:
    population = builder()
    runner = runner_factory()
    trajectory = run_trajectory(population, runner, labels)
    restart = restart_from_boundaries(builder, runner_factory, labels, trajectory)
    return {"name": name, "trajectory": trajectory, "restart": restart}


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


def trajectory_metrics(trajectory: dict[str, Any]) -> dict[str, Any]:
    snapshots = trajectory["snapshots"]
    seed_identities = set(snapshots[0]["distinct_packet_identities"])
    full_distribution_tick: int | None = None
    if seed_identities:
        for snapshot in snapshots:
            if all(seed_identities.issubset(set(cell["recoverable_packet_identities"])) for cell in snapshot["cells"].values()):
                full_distribution_tick = snapshot["tick_index"]
                break
    return {
        "final_population_digest": snapshots[-1]["population_digest"],
        "final_packet_identities": snapshots[-1]["distinct_packet_identities"],
        "final_copies_per_packet": snapshots[-1]["copies_per_packet"],
        "ticks_to_full_distribution": full_distribution_tick,
        "observed_fixed_point_ticks": [snapshot["tick_index"] for snapshot in snapshots if snapshot["state_observation"] == "OBSERVED_FIXED_POINT_WITHIN_HORIZON"],
        "observed_repeat_ticks": [snapshot["tick_index"] for snapshot in snapshots if snapshot["state_observation"] == "OBSERVED_REPEAT_WITHIN_HORIZON"],
    }


def run_scenario(name: str, builder: Callable[[], PopulationManager], labels: dict[int, str]) -> dict[str, Any]:
    baseline = run_condition("KC3D_CANONICAL", builder, lambda: population_tick, labels)
    conditions: dict[str, dict[str, Any]] = {"KC3D_CANONICAL": baseline}
    for order_name in ORDER_NAMES:
        conditions[order_name] = run_condition(
            order_name,
            builder,
            lambda order_name=order_name: lambda population: counterfactual_tick(population, order_name),
            labels,
        )
    baseline_trajectory = baseline["trajectory"]
    initial_snapshot = baseline_trajectory["snapshots"][0]
    comparisons: dict[str, Any] = {}
    for condition_name, condition in conditions.items():
        comparisons[condition_name] = {
            "initial_state_equal_to_canonical": condition["trajectory"]["snapshots"][0] == initial_snapshot,
            "metrics": trajectory_metrics(condition["trajectory"]),
        }
    return {
        "name": name,
        "conditions": conditions,
        "comparisons": comparisons,
        "ascending_matches_frozen_canonical": canonical(conditions["ascending"]["trajectory"]) == canonical(baseline_trajectory),
    }


def audit_harness_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    function_names: set[str] = set()
    while_count = 0
    async_count = 0
    bounded_range_loops = 0
    execution_mutation_calls: list[str] = []
    counterfactual_parameters: list[str] | None = None
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
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_names.add(node.name)
            if isinstance(node, ast.FunctionDef) and node.name == "counterfactual_tick":
                counterfactual_parameters = [argument.arg for argument in node.args.args]
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr in {"spawn", "kill"}:
                        execution_mutation_calls.append(child.func.attr)
        elif isinstance(node, ast.While):
            while_count += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            async_count += 1
        elif isinstance(node, ast.For):
            if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                bounded_range_loops += 1
    forbidden = sorted((names | imports) & {
        "random", "secrets", "timer", "thread", "threading", "process", "subprocess", "scheduler",
        "callback", "asyncio", "network", "socket", "fitness", "selection", "learning", "adaptive",
        "run_forever", "autorun", "run_horizon",
    })
    forbidden_functions = sorted(function_names & {"run_forever", "autorun", "run_horizon"})
    runtime_signature = [parameter.name for parameter in inspect.signature(counterfactual_tick).parameters.values()]
    expected_signature = ["population", "order_name"]
    signature_ok = runtime_signature == expected_signature and counterfactual_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and not forbidden_functions and not execution_mutation_calls and while_count == 0 and async_count == 0 and bounded_range_loops >= 1 and signature_ok and activate_calls == 1 else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "forbidden_functions": forbidden_functions,
        "execution_mutation_calls": execution_mutation_calls,
        "while_loop_count": while_count,
        "async_function_count": async_count,
        "bounded_range_loop_count": bounded_range_loops,
        "counterfactual_runtime_signature": runtime_signature,
        "counterfactual_source_signature": counterfactual_parameters,
        "direct_activate_cell_calls": activate_calls,
    }


def characterize_once(ids: dict[str, int], config: dict[str, Any]) -> dict[str, Any]:
    labels = {token: packet_id for packet_id, token in ids.items()}
    synthetic_token = 25
    labels[synthetic_token] = "synthetic_token_25_same_slot_as_p000"
    same_slot_tokens = [ids["p000"], ids["p008"], ids["p016"], synthetic_token]

    scenarios = {
        **{f"chain_seed_C{index}": run_scenario(f"chain_seed_C{index}", chain_seeded(index, ids["p007"]), labels) for index in range(4)},
        "branch_seed_root": run_scenario("branch_seed_root", branch_seeded(0, ids["p007"]), labels),
        "branch_seed_middle": run_scenario("branch_seed_middle", branch_seeded(1, ids["p007"]), labels),
        "branch_seed_leaf": run_scenario("branch_seed_leaf", branch_seeded(4, ids["p007"]), labels),
        "non_colliding_multi_packet": run_scenario("non_colliding_multi_packet", multi_packet_builder([ids["p000"], ids["p001"], ids["p002"], ids["p003"]]), labels),
        "same_slot_ascending": run_scenario("same_slot_ascending", multi_packet_builder(same_slot_tokens), labels),
        "same_slot_reversed": run_scenario("same_slot_reversed", multi_packet_builder(list(reversed(same_slot_tokens))), labels),
        "empty_population": run_scenario("empty_population", empty_population_builder, labels),
        "empty_knowledge": run_scenario("empty_knowledge", empty_knowledge_builder, labels),
        "dead_intermediate": run_scenario("dead_intermediate", dead_gap_builder(ids["p007"]), labels),
    }
    same_slot = {
        "initial_identities_ascending": [packet_label(token, labels) for token in same_slot_tokens],
        "initial_identities_reversed": [packet_label(token, labels) for token in reversed(same_slot_tokens)],
        "physical_slot": same_slot_tokens[0] % 8,
        "ascending_final_by_order": {order: scenarios["same_slot_ascending"]["comparisons"][order]["metrics"]["final_packet_identities"] for order in ORDER_NAMES},
        "reversed_final_by_order": {order: scenarios["same_slot_reversed"]["comparisons"][order]["metrics"]["final_packet_identities"] for order in ORDER_NAMES},
    }
    all_conditions = [condition for scenario in scenarios.values() for condition in scenario["conditions"].values()]
    all_restarts_pass = all(condition["restart"]["all_pass"] for condition in all_conditions)
    all_initial_states_match = all(
        comparison["initial_state_equal_to_canonical"]
        for scenario in scenarios.values()
        for condition_name, comparison in scenario["comparisons"].items()
        if condition_name != "KC3D_CANONICAL"
    )
    all_ascending_match = all(scenario["ascending_matches_frozen_canonical"] for scenario in scenarios.values())
    all_bounds_pass = all(
        condition["trajectory"]["within_total_bounds"]
        and condition["trajectory"]["registry_unchanged"]
        and condition["trajectory"]["live_ids_unchanged"]
        for condition in all_conditions
    )
    return {
        "horizon": MAX_TICKS,
        "order_names": list(ORDER_NAMES),
        "scenarios": scenarios,
        "same_slot_summary": same_slot,
        "all_initial_states_match": all_initial_states_match,
        "all_ascending_match_frozen_canonical": all_ascending_match,
        "all_restarts_pass": all_restarts_pass,
        "all_bounds_and_immutability_pass": all_bounds_pass,
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    anchor_errors: list[str] = []
    anchors = {
        "population_tick_source_sha256": TICK_PATH,
        "population_tick_config_sha256": TICK_CONFIG_PATH,
        "kc3e_characterization_source_sha256": KC3E_CHARACTERIZE_PATH,
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
    if config.get("order_names") != list(ORDER_NAMES):
        anchor_errors.append("order definitions are not frozen")
    if config.get("max_ticks") != MAX_TICKS or config.get("max_total_activations") != MAX_TOTAL_ACTIVATIONS or config.get("max_total_slot_contacts") != MAX_TOTAL_SLOT_CONTACTS:
        anchor_errors.append("horizon or total bounds are incorrect")
    if config.get("random_source") is not False or config.get("adaptive_order") is not False:
        anchor_errors.append("random or adaptive scheduling is enabled")

    source_audit = audit_harness_source(CHARACTERIZE_PATH)
    first = characterize_once(ids, config)
    second = characterize_once(ids, config)
    replay_pass = canonical(first) == canonical(second)
    scenario_count = len(first["scenarios"])
    required_scenario_names = {
        "chain_seed_C0", "chain_seed_C1", "chain_seed_C2", "chain_seed_C3",
        "branch_seed_root", "branch_seed_middle", "branch_seed_leaf",
        "non_colliding_multi_packet", "same_slot_ascending", "same_slot_reversed",
        "empty_population", "empty_knowledge", "dead_intermediate",
    }
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "source_audit": source_audit["status"] == "PASS",
        "frozen_order_set": first["order_names"] == list(ORDER_NAMES) and scenario_count == len(required_scenario_names) and set(first["scenarios"]) == required_scenario_names,
        "same_initial_state_across_orders": first["all_initial_states_match"],
        "ascending_matches_frozen_canonical": first["all_ascending_match_frozen_canonical"],
        "single_packet_chain": all(name.startswith("chain_seed_") for name in first["scenarios"] if name.startswith("chain_seed_")),
        "non_colliding_distribution": "non_colliding_multi_packet" in first["scenarios"],
        "same_slot_both_placements": set(first["same_slot_summary"]) >= {"ascending_final_by_order", "reversed_final_by_order"},
        "branching_positions": all(name in first["scenarios"] for name in ["branch_seed_root", "branch_seed_middle", "branch_seed_leaf"]),
        "dead_gap_control": "dead_intermediate" in first["scenarios"],
        "trajectory_horizon": all(
            len(condition["trajectory"]["snapshots"]) == MAX_TICKS + 1
            and len(condition["trajectory"]["ticks"]) == MAX_TICKS
            for scenario in first["scenarios"].values()
            for condition in scenario["conditions"].values()
        ),
        "restart_each_boundary": first["all_restarts_pass"],
        "hard_bounds_and_immutability": first["all_bounds_and_immutability_pass"],
        "no_random_or_adaptive_order": config.get("random_source") is False and config.get("adaptive_order") is False,
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-3F-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_3F_DEV_COMPLETE" if passed else "KC_3F_DEV_INVALID",
        "population_tick_source_sha256": sha256(TICK_PATH),
        "population_tick_config_sha256": sha256(TICK_CONFIG_PATH),
        "kc3e_characterization_source_sha256": sha256(KC3E_CHARACTERIZE_PATH),
        "activation_source_sha256": sha256(ACTIVATION_PATH),
        "manager_source_sha256": sha256(MANAGER_PATH),
        "cell_source_sha256": sha256(CELL_PATH),
        "fixture_bank_sha256": sha256(bank_path),
        "config_sha256": sha256(config_path),
        "characterize_source_sha256": sha256(CHARACTERIZE_PATH),
        "anchor_errors": anchor_errors,
        "order_definitions": config.get("order_definitions"),
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
        "source_audit": source_audit,
        "characterization": first,
        "note": "Development scheduler-counterfactual characterization only; KC-3D canonical tick remains frozen and no adaptive, random, scientific, or population-mechanism conclusion is authorized.",
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
