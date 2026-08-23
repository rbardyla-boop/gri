#!/usr/bin/env python3
"""GRI-01H: locate task information in the frozen d=8 hidden trajectory."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import linprog

EXPERIMENTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import build_examples, digest  # noqa: E402
from gri01e_representability import solve, unpack  # noqa: E402


def transition(h, token, params, index):
    embedding, matrix, bias, _, _ = params
    return np.tanh(matrix @ h + bias + embedding[index[token]])


def state_for_case(case, wait_count, params, index):
    h = np.zeros(params[1].shape[0], dtype=np.float64)
    for token in case["prefix"]:
        h = transition(h, token, params, index)
    for _ in range(wait_count):
        h = transition(h, "WAIT", params, index)
    return h


def cases_from_fixture(examples):
    cases = {}
    for task, tokens, label, _ in examples:
        query = next(token for token in tokens if token.startswith("QUERY_"))
        prefix = tuple(tokens[:tokens.index(query)])
        while prefix and prefix[-1] == "WAIT":
            prefix = prefix[:-1]
        key = (task, prefix, query, label)
        cases[key] = {
            "case_id": f"{task}:{len(cases)}",
            "task": task,
            "prefix": list(prefix),
            "query": query,
            "label": label,
        }
    return list(cases.values())


def fit_separator(states, labels, margin, tolerance):
    x = np.asarray(states, dtype=np.float64)
    y = np.where(np.asarray(labels, dtype=np.int64) == 1, 1.0, -1.0)
    augmented = np.concatenate([x, np.ones((len(x), 1), dtype=np.float64)], axis=1)
    constraints = -(y[:, None] * augmented)
    bounds = [(None, None)] * augmented.shape[1]
    result = linprog(
        np.zeros(augmented.shape[1], dtype=np.float64),
        A_ub=constraints,
        b_ub=np.full(len(x), -margin, dtype=np.float64),
        bounds=bounds,
        method="highs",
    )
    if result.x is None:
        return {
            "separator_found": False,
            "accuracy": None,
            "minimum_signed_margin": None,
            "solver_status": int(result.status),
            "solver_message": result.message,
        }
    signed_margins = y * (augmented @ result.x)
    predictions = (augmented @ result.x >= 0.0).astype(np.int64)
    accuracy = float(np.mean(predictions == (y > 0)))
    feasible = bool(result.success and np.min(signed_margins) >= margin - tolerance)
    return {
        "separator_found": feasible,
        "accuracy": accuracy,
        "minimum_signed_margin": float(np.min(signed_margins)),
        "solver_status": int(result.status),
        "solver_message": result.message,
        "weights": result.x[:-1].tolist(),
        "bias": float(result.x[-1]),
    }


def opposite_label_separation(states, labels):
    pairs = []
    for i, j in combinations(range(len(states)), 2):
        if labels[i] != labels[j]:
            pairs.append(float(np.linalg.norm(np.asarray(states[i]) - np.asarray(states[j]))))
    return {
        "pair_count": len(pairs),
        "minimum": min(pairs) if pairs else None,
        "mean": float(np.mean(pairs)) if pairs else None,
        "maximum": max(pairs) if pairs else None,
    }


def task_classification(fixed, wait_specific):
    fixed_ok = bool(fixed["separator_found"] and fixed["accuracy"] == 1.0)
    specific_ok = [bool(row["separator_found"] and row["accuracy"] == 1.0) for row in wait_specific.values()]
    if fixed_ok:
        return "FIXED_DECODER"
    if specific_ok and all(specific_ok):
        return "PHASE_ROTATED"
    if any(specific_ok):
        return "PHASE_LOCALIZED_LOSS"
    return "DECODER_FAILURE"


def overall_classification(classifications):
    values = set(classifications.values())
    if len(values) == 1:
        return next(iter(values))
    return "TASK_SPECIFIC"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01h_config.json")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS.parent / "artifacts/results/gri01h_information_location_receipt.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-01H config is not frozen")
    parent_path = args.config.with_name(config["parent_config"])
    if digest(parent_path) != config["parent_config_sha256"]:
        raise SystemExit("GRI-01G config hash mismatch")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    gri01f_path = parent_path.with_name(parent["parent_config"])
    gri01f = json.loads(gri01f_path.read_text(encoding="utf-8"))
    gri01e_path = gri01f_path.with_name(gri01f["parent_config"])
    gri01e = json.loads(gri01e_path.read_text(encoding="utf-8"))
    base_path = gri01e_path.with_name(gri01e["parent_config"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    train = build_examples(base, base["train_delays"])
    theta, solver = solve(
        train,
        base["input_alphabet"],
        config["dimension"],
        gri01e["solver"],
        gri01e["solver"]["initialization_seed_base"] + config["dimension"],
    )
    params = tuple(x.detach().numpy() for x in unpack(theta, len(base["input_alphabet"]), config["dimension"]))
    index = {token: i for i, token in enumerate(base["input_alphabet"])}
    cases = cases_from_fixture(train)

    states_by_case = []
    for case in cases:
        states_by_case.append({
            **case,
            "states": [state_for_case(case, wait, params, index).tolist() for wait in range(config["horizon"] + 1)],
        })

    tasks = sorted({case["task"] for case in states_by_case})
    task_results = {}
    for task in tasks:
        task_cases = [case for case in states_by_case if case["task"] == task]
        fixed_states = [state for case in task_cases for state in case["states"]]
        fixed_labels = [case["label"] for case in task_cases for _ in case["states"]]
        fixed = fit_separator(
            fixed_states,
            fixed_labels,
            config["decoder"]["margin"],
            config["decoder"]["feasibility_tolerance"],
        )
        fixed["per_wait_accuracy"] = []
        fixed_vector = np.asarray(fixed.get("weights", []) + [fixed.get("bias", 0.0)], dtype=np.float64)
        for wait in range(config["horizon"] + 1):
            wait_states = [case["states"][wait] for case in task_cases]
            wait_labels = [case["label"] for case in task_cases]
            if len(fixed_vector) == config["dimension"] + 1:
                augmented = np.concatenate([np.asarray(wait_states), np.ones((len(wait_states), 1))], axis=1)
                predictions = (augmented @ fixed_vector >= 0.0).astype(np.int64)
                fixed["per_wait_accuracy"].append(float(np.mean(predictions == np.asarray(wait_labels))))
            else:
                fixed["per_wait_accuracy"].append(None)

        wait_specific = {}
        separation = []
        for wait in range(config["horizon"] + 1):
            wait_states = [case["states"][wait] for case in task_cases]
            wait_labels = [case["label"] for case in task_cases]
            wait_specific[str(wait)] = fit_separator(
                wait_states,
                wait_labels,
                config["decoder"]["margin"],
                config["decoder"]["feasibility_tolerance"],
            )
            separation.append({
                "wait_steps": wait,
                **opposite_label_separation(wait_states, wait_labels),
            })
        task_results[task] = {
            "case_count": len(task_cases),
            "fixed_separator": fixed,
            "wait_specific_separators": wait_specific,
            "opposite_label_separation": separation,
            "classification": task_classification(fixed, wait_specific),
        }

    classifications = {task: result["classification"] for task, result in task_results.items()}
    receipt = {
        "unit": config["unit"],
        "verdict": overall_classification(classifications),
        "architecture_unchanged": "exact frozen GRI-01E d=8 tanh cell; decoder fitting is post hoc measurement only",
        "config_sha256": digest(args.config),
        "parent_gri01g_config_sha256": digest(parent_path),
        "gri01e_config_sha256": digest(gri01e_path),
        "gri01_config_sha256": digest(base_path),
        "implementation_sha256": digest(Path(__file__)),
        "scipy_version": scipy.__version__,
        "solver": solver,
        "dimension": config["dimension"],
        "horizon": config["horizon"],
        "hidden_state_location": config["hidden_state_location"],
        "decoder": config["decoder"],
        "states": states_by_case,
        "tasks": task_results,
        "task_classifications": classifications,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": receipt["unit"],
        "verdict": receipt["verdict"],
        "task_classifications": classifications,
        "fixed_separator_accuracy": {
            task: result["fixed_separator"]["accuracy"] for task, result in task_results.items()
        },
        "wait_specific_perfect_counts": {
            task: sum(row["separator_found"] and row["accuracy"] == 1.0 for row in result["wait_specific_separators"].values())
            for task, result in task_results.items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
