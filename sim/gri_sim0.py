#!/usr/bin/env python3
"""GRI-SIM-0 preflight/scaffolding tool.

This is infrastructure only. It intentionally refuses to execute a scientific
candidate unless a future authorized runner is wired to a frozen experiment.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

REQUIRED_EXPERIMENT_KEYS = {"schema", "experiment_id", "status", "source", "fixtures", "budgets", "precision", "scientific_run_requires"}
REQUIRED_CANDIDATE_KEYS = {"schema", "candidate_id", "authorization_id", "status", "source_sha256", "state", "parameters", "operations", "transition_class", "serialization_fields", "authorized_ablations", "optimizer_mode"}
CANONICAL_BUDGET_KEYS = (
    "persistent_state_slots_max",
    "trainable_parameters_max",
    "recurrent_operations_max",
    "recurrent_plus_query_operations_max",
)
FORBIDDEN_SOURCE_NAMES = {
    "fixture_id", "fixture_label", "held_out_label", "task_id", "delay_count",
    "sequence_index", "step_counter", "history_buffer", "phase_variable"
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require_keys(value: dict, keys: set[str], what: str) -> list[str]:
    missing = sorted(keys - set(value))
    return [f"{what}: missing key {key}" for key in missing]


def read_budgets(value: dict, what: str = "experiment") -> tuple[dict[str, int], list[str]]:
    """Read the one canonical budget vocabulary and fail closed on drift.

    Keeping this lookup in one place prevents callers from inventing aliases
    such as ``recurrent_plus_query`` and turning a malformed manifest into an
    uncaught ``KeyError`` halfway through a run.
    """
    budgets = value.get("budgets")
    if not isinstance(budgets, dict):
        return {}, [f"{what}: budgets must be an object"]
    errors = require_keys(budgets, set(CANONICAL_BUDGET_KEYS), f"{what}.budgets")
    parsed: dict[str, int] = {}
    for key in CANONICAL_BUDGET_KEYS:
        value_for_key = budgets.get(key)
        if not isinstance(value_for_key, int) or isinstance(value_for_key, bool):
            errors.append(f"{what}.budgets: invalid budget {key}")
        else:
            parsed[key] = value_for_key
    return parsed, errors


def validate_experiment(path: Path) -> dict:
    value = load_json(path)
    errors = require_keys(value, REQUIRED_EXPERIMENT_KEYS, "experiment")
    if value.get("schema") != "GRI-SIM-0-EXPERIMENT-1":
        errors.append("experiment: schema mismatch")
    _, budget_errors = read_budgets(value)
    errors.extend(budget_errors)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "sha256": sha256(path), "experiment_id": value.get("experiment_id")}


def scan_source(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    comparisons = 0
    branches = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        if isinstance(node, ast.Compare):
            comparisons += 1
        if isinstance(node, (ast.If, ast.IfExp)):
            branches += 1
    flagged = sorted(names & FORBIDDEN_SOURCE_NAMES)
    return {"comparisons": comparisons, "branches": branches, "flagged_names": flagged}


def validate_candidate(experiment_path: Path, candidate_path: Path, source_path: Path) -> dict:
    experiment = load_json(experiment_path)
    candidate = load_json(candidate_path)
    errors = require_keys(candidate, REQUIRED_CANDIDATE_KEYS, "candidate")
    if candidate.get("schema") != "GRI-SIM-0-CANDIDATE-1":
        errors.append("candidate: schema mismatch")
    if candidate.get("status") != "IMPLEMENTATION_AUTHORIZED_BEFORE_RUN":
        errors.append("candidate: no implementation authorization")
    if not candidate.get("authorization_id"):
        errors.append("candidate: authorization_id missing")
    actual_source_hash = sha256(source_path)
    if candidate.get("source_sha256") != actual_source_hash:
        errors.append("candidate: source hash mismatch")

    budgets, budget_errors = read_budgets(experiment)
    errors.extend(budget_errors)
    state = candidate.get("state", {})
    params = candidate.get("parameters", {})
    ops = candidate.get("operations", {})
    if budgets and state.get("persistent_slots", 10**9) > budgets["persistent_state_slots_max"]:
        errors.append("candidate: persistent state budget exceeded")
    for key in ("auxiliary_slots", "history_buffer", "step_counter", "phase_variable"):
        if state.get(key) not in (0, False):
            errors.append(f"candidate: forbidden undeclared machinery {key}")
    if state.get("rng_as_state") is not False:
        errors.append("candidate: RNG-as-state forbidden")
    if not isinstance(params.get("trainable"), int) or (budgets and params["trainable"] > budgets["trainable_parameters_max"]):
        errors.append("candidate: parameter budget missing/exceeded")
    if not isinstance(ops.get("recurrent"), int) or (budgets and ops["recurrent"] > budgets["recurrent_operations_max"]):
        errors.append("candidate: recurrent operation budget missing/exceeded")
    rq = None
    if isinstance(ops.get("recurrent"), int) and isinstance(ops.get("query"), int):
        rq = ops["recurrent"] + ops["query"]
        if budgets and rq > budgets["recurrent_plus_query_operations_max"]:
            errors.append("candidate: recurrent+query operation budget exceeded")
    if ops.get("accounting_audit") != "PASS":
        errors.append("candidate: independent accounting audit not PASS")

    scan = scan_source(source_path)
    if scan["flagged_names"]:
        errors.append("candidate: suspicious source identifiers: " + ", ".join(scan["flagged_names"]))

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "candidate_id": candidate.get("candidate_id"),
        "source_sha256": actual_source_hash,
        "declared_recurrent_plus_query": rq,
        "source_scan": scan,
        "note": "AST scan is advisory; formal accounting remains independently required."
    }


def scaffold(name: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    template_dir = Path(__file__).resolve().parent
    source = (template_dir / "candidate_template.py").read_text(encoding="utf-8")
    manifest = load_json(template_dir / "candidate_manifest.example.json")
    manifest["candidate_id"] = name
    (out / "candidate.py").write_text(source, encoding="utf-8")
    (out / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "AUTHORIZATION_REQUIRED.txt").write_text("No candidate mechanism may be implemented or run scientifically until a separate authorization names this candidate.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate-experiment")
    p.add_argument("--experiment", type=Path, required=True)
    p = sub.add_parser("validate-candidate")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p = sub.add_parser("scaffold")
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "validate-experiment":
        result = validate_experiment(args.experiment)
    elif args.command == "validate-candidate":
        result = validate_candidate(args.experiment, args.candidate, args.source)
    else:
        scaffold(args.name, args.out)
        result = {"status": "SCAFFOLDED", "path": str(args.out), "candidate": args.name}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS", "SCAFFOLDED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
