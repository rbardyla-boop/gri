#!/usr/bin/env python3
"""GRI-01G: normal WAIT versus a frozen identity-WAIT counterfactual."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

EXPERIMENTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import build_examples, digest  # noqa: E402
from gri01e_representability import solve, unpack  # noqa: E402


def transition(h, token, params, index):
    embedding, matrix, bias, _, _ = params
    return np.tanh(matrix @ h + bias + embedding[index[token]])


def evaluate_case(prefix, query, label, wait_count, params, index, identity_wait):
    h = np.zeros(params[1].shape[0], dtype=np.float64)
    for token in prefix:
        h = transition(h, token, params, index)
    for _ in range(wait_count):
        if not identity_wait:
            h = transition(h, "WAIT", params, index)
    queried = transition(h, query, params, index)
    logits = params[3] @ queried + params[4]
    return int(np.argmax(logits)) == label, logits.tolist()


def cases_from_fixture(examples):
    cases = {}
    for task, tokens, label, _ in examples:
        query = next(token for token in tokens if token.startswith("QUERY_"))
        prefix = tuple(tokens[:tokens.index(query)])
        while prefix and prefix[-1] == "WAIT":
            prefix = prefix[:-1]
        cases[(task, prefix, query, label)] = {"task": task, "prefix": list(prefix), "query": query, "label": label}
    return list(cases.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01g_config.json")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS.parent / "artifacts/results/gri01g_wait_semantics_receipt.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-01G config is not frozen")
    parent_path = args.config.with_name(config["parent_config"])
    if digest(parent_path) != config["parent_config_sha256"]:
        raise SystemExit("GRI-01F config hash mismatch")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    gri01e_path = parent_path.with_name(parent["parent_config"])
    gri01e = json.loads(gri01e_path.read_text(encoding="utf-8"))
    base_path = gri01e_path.with_name(gri01e["parent_config"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    train = build_examples(base, base["train_delays"])
    theta, solver = solve(train, base["input_alphabet"], config["dimension"], gri01e["solver"], gri01e["solver"]["initialization_seed_base"] + config["dimension"])
    params = tuple(x.detach().numpy() for x in unpack(theta, len(base["input_alphabet"]), config["dimension"]))
    index = {token: i for i, token in enumerate(base["input_alphabet"])}
    cases = cases_from_fixture(train)
    matrix = []
    for wait_count in range(config["horizon"] + 1):
        row = {"wait_steps": wait_count, "tasks": {}}
        for task in sorted({case["task"] for case in cases}):
            task_cases = [case for case in cases if case["task"] == task]
            normal_results = [evaluate_case(case["prefix"], case["query"], case["label"], wait_count, params, index, False) for case in task_cases]
            identity_results = [evaluate_case(case["prefix"], case["query"], case["label"], wait_count, params, index, True) for case in task_cases]
            row["tasks"][task] = {
                "normal_accuracy": sum(x[0] for x in normal_results) / len(normal_results),
                "identity_wait_accuracy": sum(x[0] for x in identity_results) / len(identity_results),
                "normal_logits": [x[1] for x in normal_results],
                "identity_wait_logits": [x[1] for x in identity_results],
            }
        matrix.append(row)
    normal_values = [value for row in matrix for value in row["tasks"].values()]
    normal_success = any(value["normal_accuracy"] == 1.0 for value in normal_values)
    normal_failure = any(value["normal_accuracy"] < 1.0 for value in normal_values)
    identity_perfect = all(value["identity_wait_accuracy"] == 1.0 for value in normal_values)
    if identity_perfect and normal_failure:
        verdict = "IDENTITY_WAIT_WORKS"
    elif normal_success and normal_failure and not identity_perfect:
        verdict = "TRANSIENT_CODING"
    else:
        verdict = "NEITHER"
    receipt = {
        "unit": config["unit"], "verdict": verdict,
        "config_sha256": digest(args.config), "parent_gri01f_config_sha256": digest(parent_path),
        "gri01e_config_sha256": digest(gri01e_path), "gri01_config_sha256": digest(base_path),
        "solver": solver, "dimension": config["dimension"], "horizon": config["horizon"],
        "cases": cases, "matrix": matrix,
        "identity_wait": config["identity_wait_counterfactual"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    summary = {task: [{"wait": row["wait_steps"], "normal": row["tasks"][task]["normal_accuracy"], "identity": row["tasks"][task]["identity_wait_accuracy"]} for row in matrix] for task in sorted({case["task"] for case in cases})}
    print(json.dumps({"unit": receipt["unit"], "verdict": verdict, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
