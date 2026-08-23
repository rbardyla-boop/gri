#!/usr/bin/env python3
"""GRI-01E: deterministic constructive representability test.

The frozen cell is exactly h'=tanh(W h + b + E[token]); logits=O h + c.
Torch LBFGS is used only as a fixed deterministic solver, not as a replacement
training setup or a source of post-result tuning.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch import Tensor

EXPERIMENTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import build_examples, canonical, digest, encode, fixture_hash  # noqa: E402


def unpack(theta: Tensor, k: int, d: int):
    cursor = 0
    embedding = theta[cursor:cursor + k * d].reshape(k, d); cursor += k * d
    transition = theta[cursor:cursor + d * d].reshape(d, d); cursor += d * d
    bias = theta[cursor:cursor + d]; cursor += d
    readout = theta[cursor:cursor + 2 * d].reshape(2, d); cursor += 2 * d
    readout_bias = theta[cursor:cursor + 2]
    return embedding, transition, bias, readout, readout_bias


def logits(theta, inputs, lengths, k, d):
    embedding, transition, bias, readout, readout_bias = unpack(theta, k, d)
    h = torch.zeros(inputs.shape[0], d, dtype=theta.dtype)
    final = torch.zeros_like(h)
    for step in range(inputs.shape[1]):
        h = torch.tanh(h @ transition.T + bias + embedding[inputs[:, step]])
        active = lengths == step + 1
        final = torch.where(active[:, None], h, final)
    return final @ readout.T + readout_bias


def evaluate(theta, examples, alphabet, d):
    inputs, lengths, labels, _ = encode(examples, alphabet)
    with torch.no_grad():
        values = logits(theta, inputs, lengths, len(alphabet), d)
    observed = values.argmax(1)
    cells = {}
    failures = []
    for row, (task, _, label, delay) in enumerate(examples):
        cell = cells.setdefault((task, delay), {"correct": 0, "total": 0})
        cell["total"] += 1
        if int(observed[row]) == label:
            cell["correct"] += 1
        else:
            failures.append({"task": task, "delay": delay, "label": label, "observed": int(observed[row]), "logits": values[row].tolist()})
    rows = [{"task": task, "delay": delay, "correct": cell["correct"], "total": cell["total"], "accuracy": cell["correct"] / cell["total"]} for (task, delay), cell in sorted(cells.items())]
    total = sum(x["total"] for x in cells.values())
    correct = sum(x["correct"] for x in cells.values())
    return {"accuracy": correct / total, "cells": rows, "failures": failures}


def solve(train, alphabet, d, solver_config, seed):
    inputs, lengths, labels, _ = encode(train, alphabet)
    k = len(alphabet)
    count = k * d + d * d + d + 2 * d + 2
    generator = torch.Generator().manual_seed(seed)
    theta = torch.randn(count, generator=generator, dtype=torch.float64) * 0.1
    theta.requires_grad_(True)
    target = torch.where(labels[:, None] == torch.tensor([0, 1]), 1.0, -1.0) * solver_config["target_logit_margin"]
    optimizer = torch.optim.LBFGS(
        [theta], lr=solver_config["learning_rate"], max_iter=solver_config["max_iter"],
        tolerance_grad=solver_config["tolerance_grad"], tolerance_change=solver_config["tolerance_change"],
        line_search_fn=solver_config["line_search"],
    )
    calls = 0
    def closure():
        nonlocal calls
        calls += 1
        optimizer.zero_grad()
        loss = (logits(theta, inputs, lengths, k, d) - target).square().mean()
        loss.backward()
        return loss
    initial_loss = float(closure().detach())
    optimizer.step(closure)
    final_loss = float(closure().detach())
    return theta.detach(), {"parameter_count": count, "initial_loss": initial_loss, "final_loss": final_loss, "closure_calls": calls}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01e_config.json")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS.parent / "artifacts/results/gri01e_representability_receipt.json")
    args = parser.parse_args()
    experiment = json.loads(args.config.read_text(encoding="utf-8"))
    if experiment.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-01E config is not frozen")
    parent_path = args.config.with_name(experiment["parent_config"])
    if digest(parent_path) != experiment["parent_config_sha256"]:
        raise SystemExit("parent GRI-01 config hash mismatch")
    config = json.loads(parent_path.read_text(encoding="utf-8"))
    torch.use_deterministic_algorithms(True)
    alphabet = config["input_alphabet"]
    train = build_examples(config, config["train_delays"])
    test = build_examples(config, config["test_delays"])
    results = []
    for d in config["dimensions"]:
        theta, solver = solve(train, alphabet, d, experiment["solver"], experiment["solver"]["initialization_seed_base"] + d)
        train_result = evaluate(theta, train, alphabet, d)
        test_result = evaluate(theta, test, alphabet, d)
        results.append({"dimension": d, "solver": solver, "train": train_result, "test": test_result})
    train_pass = all(r["train"]["accuracy"] == 1.0 for r in results)
    test_pass = all(r["test"]["accuracy"] == 1.0 for r in results)
    if train_pass and test_pass:
        verdict = "REPRESENTABLE"
    elif any(r["train"]["accuracy"] == 1.0 and r["test"]["accuracy"] < 1.0 for r in results):
        verdict = "PARTIAL_GENERALIZATION"
    else:
        verdict = "NO_CONSTRUCTION_FOUND"
    receipt = {
        "unit": experiment["unit"], "verdict": verdict,
        "architecture": "h'=tanh(W h + b + E[token]); logits=O h + c",
        "config_sha256": digest(args.config), "parent_config_sha256": digest(parent_path),
        "implementation_sha256": digest(Path(__file__)),
        "train_fixture_sha256": fixture_hash(train, alphabet), "test_fixture_sha256": fixture_hash(test, alphabet),
        "solver_config": experiment["solver"], "results": results,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(receipt))
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
