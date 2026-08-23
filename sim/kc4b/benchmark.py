#!/usr/bin/env python3
"""KC-4B-D bounded capacity/redundancy frontier characterization."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from sim.kc0.kc1a.cell import STATE_BYTES_MAX
from sim.kc0.validate_bank import sha256
from sim.kc2b.export import export_slot
from sim.kc3a.manager import PopulationManager
from sim.kc3d.tick import population_tick
from sim.runtime import canonical, tensor_digest


FIXTURE_PATH = HERE / "fixtures.json"
CONFIG_PATH = HERE / "config.json"
BENCHMARK_PATH = HERE / "benchmark.py"
TICK_PATH = ROOT / "sim" / "kc3d" / "tick.py"
TICK_CONFIG_PATH = ROOT / "sim" / "kc3d" / "config.json"
MANAGER_PATH = ROOT / "sim" / "kc3a" / "manager.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"

SLOT_COUNT = 64
CELL_COUNT = 8
SLOTS_PER_CELL = 8
HORIZON_TICKS = 4
MAX_KC_ACTIVATIONS = 32
MAX_KC_CONTACTS = 448
DECLARED_STATE_BYTES = 1024


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def token_label(token: int) -> str:
    return f"token_{token:02d}"


class EqualRedundancy64:
    """A simple static 64-address store with the same duplicate placements."""

    schema = "KC-4B-EQUAL-REDUNDANCY-64-1"

    def __init__(self) -> None:
        self.values: list[int | None] = [None] * SLOT_COUNT
        self.occupied: list[bool] = [False] * SLOT_COUNT
        self.write_count = 0

    def write(self, address: int, token: int) -> None:
        if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < SLOT_COUNT:
            raise ValueError("baseline address is invalid")
        if isinstance(token, bool) or not isinstance(token, int) or not 0 <= token <= 65534:
            raise ValueError("baseline token is invalid")
        self.values[address] = token
        self.occupied[address] = True
        self.write_count += 1

    def remove_addresses(self, addresses: list[int]) -> None:
        for address in addresses:
            if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < SLOT_COUNT:
                raise ValueError("baseline failure address is invalid")
            self.values[address] = None
            self.occupied[address] = False

    def tokens(self) -> list[int]:
        return [value for value, occupied in zip(self.values, self.occupied) if occupied and value is not None]

    def digest(self) -> str:
        return hashlib.sha256(canonical({"schema": self.schema, "values": self.values, "occupied": self.occupied}).encode("utf-8")).hexdigest()

    def serialize(self) -> bytes:
        return canonical({"schema": self.schema, "values": self.values, "occupied": self.occupied}).encode("utf-8")

    @classmethod
    def restore(cls, payload: bytes) -> "EqualRedundancy64":
        document = json.loads(payload.decode("utf-8"))
        if set(document) != {"schema", "values", "occupied"} or document["schema"] != cls.schema:
            raise ValueError("invalid baseline payload")
        if not isinstance(document["values"], list) or len(document["values"]) != SLOT_COUNT:
            raise ValueError("baseline values are invalid")
        if not isinstance(document["occupied"], list) or len(document["occupied"]) != SLOT_COUNT:
            raise ValueError("baseline occupancy is invalid")
        if any(not isinstance(value, bool) for value in document["occupied"]):
            raise ValueError("baseline occupancy contains non-booleans")
        if any(occupied and (not isinstance(value, int) or isinstance(value, bool)) for value, occupied in zip(document["values"], document["occupied"])):
            raise ValueError("baseline occupied value is invalid")
        restored = cls()
        restored.values = list(document["values"])
        restored.occupied = list(document["occupied"])
        return restored


def full_population() -> PopulationManager:
    population = PopulationManager()
    founder = population.create_founder()
    first = population.spawn(founder)
    left = population.spawn(first)
    right = population.spawn(first)
    population.spawn(left)
    population.spawn(left)
    population.spawn(right)
    population.spawn(right)
    return population


def profile_tokens(profile: dict[str, Any]) -> set[int]:
    return {token for values in profile["placements"].values() for token in values}


def seed_population(population: PopulationManager, profile: dict[str, Any]) -> None:
    for cell_id in sorted(profile["placements"], key=lambda value: int(value[1:])):
        for token in profile["placements"][cell_id]:
            population.consume(cell_id, token)


def state_tokens(state: torch.Tensor) -> list[int]:
    return [
        token
        for slot_id in range(SLOTS_PER_CELL)
        for token in [export_slot(state, slot_id)]
        if token is not None
    ]


def packet_counts(tokens: list[int]) -> dict[str, int]:
    return dict(sorted((token_label(token), count) for token, count in Counter(tokens).items()))


def packet_cells(population: PopulationManager) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for cell_id in population.live_ids():
        for token in sorted(set(state_tokens(population.state_snapshot(cell_id)))):
            result.setdefault(token_label(token), []).append(cell_id)
    return dict(sorted(result.items()))


def kc_snapshot(population: PopulationManager, tick_index: int, expected_tokens: set[int], previous_digest: str | None) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = {}
    all_tokens: list[int] = []
    for cell_id in population.live_ids():
        state = population.state_snapshot(cell_id)
        tokens = state_tokens(state)
        all_tokens.extend(tokens)
        cells[cell_id] = {
            "state_sha256": tensor_digest(state),
            "recoverable_packet_identities": [token_label(token) for token in sorted(set(tokens))],
            "occupied_slot_count": len(tokens),
        }
    counts = packet_counts(all_tokens)
    identities = set(counts)
    expected = {token_label(token) for token in expected_tokens}
    recovered = identities & expected
    digest = population.population_digest()
    return {
        "tick_index": tick_index,
        "registry": population.registry_snapshot(),
        "live_ids": population.live_ids(),
        "cells": cells,
        "state_sha256": digest,
        "recoverable_packet_identities": sorted(identities),
        "copies_per_packet": counts,
        "cells_containing_packet": packet_cells(population),
        "occupied_physical_slots": len(all_tokens),
        "storage_utilization": len(all_tokens) / SLOT_COUNT,
        "changed_since_previous_tick": False if previous_digest is None else digest != previous_digest,
        "expected_packet_count": len(expected),
        "recovered_packet_count": len(recovered),
        "missing_packet_identities": sorted(expected - identities),
        "unexpected_packet_identities": sorted(identities - expected),
    }


def central_snapshot(memory: EqualRedundancy64, tick_index: int, expected_tokens: set[int], previous_digest: str | None) -> dict[str, Any]:
    tokens = memory.tokens()
    counts = packet_counts(tokens)
    identities = set(counts)
    expected = {token_label(token) for token in expected_tokens}
    digest = memory.digest()
    return {
        "tick_index": tick_index,
        "state_sha256": digest,
        "recoverable_packet_identities": sorted(identities),
        "copies_per_packet": counts,
        "occupied_physical_slots": len(tokens),
        "storage_utilization": len(tokens) / SLOT_COUNT,
        "changed_since_previous_tick": False if previous_digest is None else digest != previous_digest,
        "expected_packet_count": len(expected),
        "recovered_packet_count": len(identities & expected),
        "missing_packet_identities": sorted(expected - identities),
        "unexpected_packet_identities": sorted(identities - expected),
    }


def run_kc_trajectory(population: PopulationManager, expected_tokens: set[int], start_tick: int = 0, initial_previous_digest: str | None = None) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    ticks: list[dict[str, Any]] = []
    previous_digest = initial_previous_digest
    snapshots.append(kc_snapshot(population, start_tick, expected_tokens, previous_digest))
    total_activations = 0
    total_contacts = 0
    for tick_index in range(start_tick + 1, HORIZON_TICKS + 1):
        tick = population_tick(population)
        total_activations += int(tick["activation_count"])
        total_contacts += int(tick["contact_count"])
        ticks.append({
            "tick_index": tick_index,
            "activation_order": tick["activation_order"],
            "activation_count": tick["activation_count"],
            "slot_contact_count": tick["contact_count"],
            "delivery_count": tick["delivery_count"],
        })
        previous_digest = snapshots[-1]["state_sha256"]
        snapshots.append(kc_snapshot(population, tick_index, expected_tokens, previous_digest))
    return {
        "snapshots": snapshots,
        "ticks": ticks,
        "total_activations": total_activations,
        "total_slot_contacts": total_contacts,
        "operations": total_activations + total_contacts,
        "within_bounds": total_activations <= MAX_KC_ACTIVATIONS and total_contacts <= MAX_KC_CONTACTS,
    }


def kc_restart_pass(builder: Callable[[], PopulationManager], expected_tokens: set[int], baseline: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for boundary in range(HORIZON_TICKS):
        population = builder()
        for _ in range(boundary):
            population_tick(population)
        restored = PopulationManager.restore(population.serialize())
        previous_digest = baseline["snapshots"][boundary - 1]["state_sha256"] if boundary else None
        resumed = run_kc_trajectory(restored, expected_tokens, start_tick=boundary, initial_previous_digest=previous_digest)
        expected = {"snapshots": baseline["snapshots"][boundary:], "ticks": baseline["ticks"][boundary:]}
        actual = {"snapshots": resumed["snapshots"], "ticks": resumed["ticks"]}
        results.append({"boundary": boundary, "match": canonical(actual) == canonical(expected)})
    return {"boundaries": results, "all_pass": all(result["match"] for result in results)}


def build_baseline(profile: dict[str, Any]) -> EqualRedundancy64:
    memory = EqualRedundancy64()
    for cell_index, cell_id in enumerate(sorted(profile["placements"], key=lambda value: int(value[1:]))):
        values = profile["placements"][cell_id]
        for slot_id, token in enumerate(values):
            memory.write(cell_index * SLOTS_PER_CELL + slot_id, token)
    return memory


def run_central_trajectory(memory: EqualRedundancy64, expected_tokens: set[int]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    previous_digest: str | None = None
    for tick_index in range(HORIZON_TICKS + 1):
        snapshots.append(central_snapshot(memory, tick_index, expected_tokens, previous_digest))
        previous_digest = snapshots[-1]["state_sha256"]
    return {
        "snapshots": snapshots,
        "ticks": [],
        "initialization_writes": memory.write_count,
        "runtime_communications": 0,
        "runtime_operations": 0,
        "operations": memory.write_count,
        "within_bounds": memory.write_count == SLOT_COUNT,
    }


def central_restart_pass(profile: dict[str, Any], expected_tokens: set[int], baseline: dict[str, Any], failure_addresses: list[int], failure_phase: str | None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for boundary in range(HORIZON_TICKS):
        memory = build_baseline(profile)
        if failure_phase == "before_ticks":
            memory.remove_addresses(failure_addresses)
        restored = EqualRedundancy64.restore(memory.serialize())
        actual = run_central_trajectory(restored, expected_tokens)["snapshots"][boundary:]
        expected = baseline["snapshots"][boundary:]
        results.append({"boundary": boundary, "match": canonical(actual) == canonical(expected)})
    return {"boundaries": results, "all_pass": all(result["match"] for result in results)}


def metrics(trajectory: dict[str, Any], final_snapshot: dict[str, Any], state_bytes: int, logical_slots: int, communications: int, operations: int, restart_pass: bool) -> dict[str, Any]:
    expected_count = final_snapshot["expected_packet_count"]
    recovered_count = final_snapshot["recovered_packet_count"]
    return {
        "logical_slots": logical_slots,
        "declared_state_bytes": state_bytes,
        "expected_unique_identities": expected_count,
        "unique_identities_retained": recovered_count,
        "unique_identities_lost": len(final_snapshot["missing_packet_identities"]),
        "recovery_rate": recovered_count / expected_count if expected_count else 1.0,
        "missing_packet_identities": final_snapshot["missing_packet_identities"],
        "unexpected_packet_identities": final_snapshot["unexpected_packet_identities"],
        "copies_per_identity": final_snapshot["copies_per_packet"],
        "copy_count_histogram": dict(sorted((str(count), list(final_snapshot["copies_per_packet"].values()).count(count)) for count in set(final_snapshot["copies_per_packet"].values()))),
        "occupied_physical_slots": final_snapshot["occupied_physical_slots"],
        "storage_utilization": final_snapshot["storage_utilization"],
        "final_state_sha256": final_snapshot["state_sha256"],
        "communication_contacts": communications,
        "operations": operations,
        "restart_pass": restart_pass,
        "horizon_ticks": HORIZON_TICKS,
        "trajectory_tick_count": len(trajectory["snapshots"]) - 1,
    }


def case_list(fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for level in sorted(fixtures["redundancy_levels"], key=int):
        cases.append({"name": f"r{level}_no_failure", "profile": level, "failure": None})
        for phase in ("before_ticks", "after_ticks"):
            for cell_id in fixtures["population_ids"]:
                cases.append({
                    "name": f"r{level}_{phase}_{cell_id}",
                    "profile": level,
                    "failure": {"cell": cell_id, "phase": phase},
                })
    return cases


def run_case(case: dict[str, Any], fixtures: dict[str, Any]) -> dict[str, Any]:
    profile = fixtures["redundancy_levels"][case["profile"]]
    expected_tokens = profile_tokens(profile)
    failure = case["failure"]
    failure_cell = failure["cell"] if failure else None
    failure_phase = failure["phase"] if failure else None

    def kc_builder() -> PopulationManager:
        population = full_population()
        seed_population(population, profile)
        if failure_phase == "before_ticks" and failure_cell is not None:
            population.kill(failure_cell)
        return population

    kc_population = kc_builder()
    kc_trajectory = run_kc_trajectory(kc_population, expected_tokens)
    kc_post_failure = None
    if failure_phase == "after_ticks" and failure_cell is not None:
        kc_population.kill(failure_cell)
        kc_post_failure = kc_snapshot(kc_population, HORIZON_TICKS, expected_tokens, kc_trajectory["snapshots"][-1]["state_sha256"])
    kc_final = kc_post_failure or kc_trajectory["snapshots"][-1]
    kc_restart = kc_restart_pass(kc_builder, expected_tokens, kc_trajectory)
    kc_metrics = metrics(
        kc_trajectory,
        kc_final,
        CELL_COUNT * STATE_BYTES_MAX,
        CELL_COUNT * SLOTS_PER_CELL,
        kc_trajectory["total_slot_contacts"],
        CELL_COUNT * SLOTS_PER_CELL + kc_trajectory["operations"],
        kc_restart["all_pass"],
    )

    baseline = build_baseline(profile)
    failure_addresses = []
    if failure_cell is not None:
        cell_index = int(failure_cell[1:])
        failure_addresses = list(range(cell_index * SLOTS_PER_CELL, (cell_index + 1) * SLOTS_PER_CELL))
    if failure_phase == "before_ticks":
        baseline.remove_addresses(failure_addresses)
    central_trajectory = run_central_trajectory(baseline, expected_tokens)
    central_post_failure = None
    if failure_phase == "after_ticks" and failure_addresses:
        baseline.remove_addresses(failure_addresses)
        central_post_failure = central_snapshot(baseline, HORIZON_TICKS, expected_tokens, central_trajectory["snapshots"][-1]["state_sha256"])
    central_final = central_post_failure or central_trajectory["snapshots"][-1]
    central_restart = central_restart_pass(profile, expected_tokens, central_trajectory, failure_addresses, failure_phase)
    central_metrics = metrics(
        central_trajectory,
        central_final,
        DECLARED_STATE_BYTES,
        SLOT_COUNT,
        central_trajectory["runtime_communications"],
        central_trajectory["operations"],
        central_restart["all_pass"],
    )
    return {
        "name": case["name"],
        "profile": case["profile"],
        "failure": failure,
        "expected_packet_identities": [token_label(token) for token in sorted(expected_tokens)],
        "kc": {"trajectory": kc_trajectory, "post_failure": kc_post_failure, "metrics": kc_metrics, "restart": kc_restart},
        "equal_redundancy_baseline": {"trajectory": central_trajectory, "post_failure": central_post_failure, "metrics": central_metrics, "restart": central_restart},
        "equal_budget": {
            "logical_slots_equal": kc_metrics["logical_slots"] == central_metrics["logical_slots"] == SLOT_COUNT,
            "declared_state_bytes_equal": kc_metrics["declared_state_bytes"] == central_metrics["declared_state_bytes"] == DECLARED_STATE_BYTES,
        },
    }


def validate_frontier(fixtures: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if fixtures.get("schema") != "KC-4B-D-CAPACITY-REDUNDANCY-FIXTURES-1":
        errors.append("fixture schema mismatch")
    if fixtures.get("logical_slot_budget") != SLOT_COUNT or fixtures.get("declared_state_bytes") != DECLARED_STATE_BYTES:
        errors.append("fixture budget mismatch")
    if fixtures.get("population_ids") != [f"C{index}" for index in range(CELL_COUNT)]:
        errors.append("population ids mismatch")
    for level, profile in fixtures.get("redundancy_levels", {}).items():
        placements = profile.get("placements", {})
        if set(placements) != set(fixtures["population_ids"]):
            errors.append(f"{level}: placement cell set mismatch")
            continue
        values = [token for cell_id in fixtures["population_ids"] for token in placements[cell_id]]
        if len(values) != SLOT_COUNT or any(not isinstance(token, int) or isinstance(token, bool) or not 0 <= token <= 65534 for token in values):
            errors.append(f"{level}: placement values invalid")
        if any(token % SLOTS_PER_CELL != slot_id for cell_id in fixtures["population_ids"] for slot_id, token in enumerate(placements[cell_id])):
            errors.append(f"{level}: token-to-slot placement mismatch")
        if len(set(values)) != profile.get("expected_unique_identities"):
            errors.append(f"{level}: unique identity count mismatch")
        if any(count != profile.get("copies_per_identity") for count in Counter(values).values()):
            errors.append(f"{level}: redundancy count mismatch")
    return errors


def audit_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
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
        elif isinstance(node, ast.While):
            while_count += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            async_count += 1
        elif isinstance(node, ast.For):
            if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                bounded_range_loops += 1
        elif isinstance(node, ast.FunctionDef) and node.name in {"run_kc_trajectory", "kc_restart_pass", "run_central_trajectory", "central_restart_pass"}:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr in {"spawn", "kill"}:
                    execution_mutation_calls.append(child.func.attr)
    forbidden = sorted((names | imports) & {"random", "secrets", "timer", "thread", "threading", "process", "subprocess", "network", "socket", "scheduler", "fitness", "selection", "learning", "adaptive", "background"})
    return {
        "status": "PASS" if not forbidden and not execution_mutation_calls and while_count == 0 and async_count == 0 and bounded_range_loops >= 1 else "FAIL",
        "forbidden_names_or_imports": forbidden,
        "execution_mutation_calls": execution_mutation_calls,
        "while_loop_count": while_count,
        "async_function_count": async_count,
        "bounded_range_loop_count": bounded_range_loops,
        "equal_redundancy_baseline_present": "EqualRedundancy64" in names,
    }


def characterize_once(fixtures: dict[str, Any]) -> dict[str, Any]:
    cases = [run_case(case, fixtures) for case in case_list(fixtures)]
    return {
        "horizon_ticks": HORIZON_TICKS,
        "case_count": len(cases),
        "cases": cases,
        "all_restart_pass": all(case["kc"]["metrics"]["restart_pass"] and case["equal_redundancy_baseline"]["metrics"]["restart_pass"] for case in cases),
        "all_equal_budget": all(all(case["equal_budget"].values()) for case in cases),
        "all_runtime_bounds": all(case["kc"]["trajectory"]["within_bounds"] for case in cases),
        "all_baseline_write_bounds": all(case["equal_redundancy_baseline"]["trajectory"]["within_bounds"] for case in cases),
        "frontier_t0": {
            level: {
                "kc": next(case for case in cases if case["name"] == f"r{level}_no_failure")["kc"]["trajectory"]["snapshots"][0],
                "baseline": next(case for case in cases if case["name"] == f"r{level}_no_failure")["equal_redundancy_baseline"]["trajectory"]["snapshots"][0],
            }
            for level in sorted(fixtures["redundancy_levels"], key=int)
        },
    }


def characterize(fixture_path: Path = FIXTURE_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    fixtures = load_json(fixture_path)
    config = load_json(config_path)
    anchor_errors: list[str] = []
    anchors = {
        "fixture_sha256": fixture_path,
        "kc3d_tick_source_sha256": TICK_PATH,
        "kc3d_tick_config_sha256": TICK_CONFIG_PATH,
        "kc3a_manager_source_sha256": MANAGER_PATH,
        "kc1a_cell_source_sha256": CELL_PATH,
    }
    for field, path in anchors.items():
        if sha256(path) != config.get(field):
            anchor_errors.append(f"{field} mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not characterization-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")
    frontier_errors = validate_frontier(fixtures)
    source_audit = audit_source(BENCHMARK_PATH)
    first = characterize_once(fixtures)
    second = characterize_once(fixtures)
    replay_pass = canonical(first) == canonical(second)
    levels = sorted(fixtures.get("redundancy_levels", {}), key=int)
    checks = {
        "anchors": not anchor_errors,
        "fixture_schema_and_frontier": not frontier_errors,
        "source_audit": source_audit["status"] == "PASS",
        "required_redundancy_levels": levels == ["1", "2", "4", "8"],
        "required_single_cell_loss_cases": first["case_count"] == len(levels) * (1 + 2 * CELL_COUNT),
        "equal_budget": first["all_equal_budget"],
        "runtime_bounds": first["all_runtime_bounds"],
        "baseline_write_bounds": first["all_baseline_write_bounds"],
        "restart": first["all_restart_pass"],
        "replay": replay_pass,
        "no_scientific_threshold": config.get("scientific_thresholds") == "UNDEFINED_IN_DEVELOPMENT" and config.get("scientific_verdict") == "FORBIDDEN",
        "no_protocol_change": config.get("protocol_change") is False and config.get("routing") is False and config.get("learning") is False and config.get("selection") is False,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-4B-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_4B_DEV_COMPLETE" if passed else "KC_4B_DEV_INVALID",
        "fixture_sha256": sha256(fixture_path),
        "config_sha256": sha256(config_path),
        "benchmark_source_sha256": sha256(BENCHMARK_PATH),
        "kc3d_tick_source_sha256": sha256(TICK_PATH),
        "kc3d_tick_config_sha256": sha256(TICK_CONFIG_PATH),
        "kc3a_manager_source_sha256": sha256(MANAGER_PATH),
        "kc1a_cell_source_sha256": sha256(CELL_PATH),
        "anchor_errors": anchor_errors,
        "frontier_errors": frontier_errors,
        "budget": {"logical_slots": SLOT_COUNT, "declared_state_bytes": DECLARED_STATE_BYTES, "kc_cells": CELL_COUNT, "slots_per_cell": SLOTS_PER_CELL},
        "redundancy_levels": [int(level) for level in levels],
        "horizon_ticks": HORIZON_TICKS,
        "checks": checks,
        "source_audit": source_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "advantage_claim": "NOT_COMPUTED",
        "characterization": first,
        "note": "Development-only capacity/redundancy frontier characterization using unchanged KC-3D propagation and an equally redundant static 64-address baseline; no routing change, threshold, or scientific verdict.",
    }
    receipt["canonical_receipt_sha256"] = hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = characterize(args.fixtures, args.config, args.receipt)
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
