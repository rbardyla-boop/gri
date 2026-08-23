#!/usr/bin/env python3
"""GRI-01F: inspect state separation under repeated frozen WAIT updates."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

EXPERIMENTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import build_examples, digest  # noqa: E402
from gri01e_representability import solve, unpack  # noqa: E402


def cosine(a, b):
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / den) if den else 1.0


def state_after(prefix, embedding, transition, bias, index):
    h = np.zeros(transition.shape[0], dtype=np.float64)
    for token in prefix:
        h = np.tanh(transition @ h + bias + embedding[index[token]])
    return h


def wait_step(h, embedding, transition, bias, index):
    return np.tanh(transition @ h + bias + embedding[index["WAIT"]])


def query_margin(h, query, label, embedding, transition, bias, readout, readout_bias, index):
    queried = np.tanh(transition @ h + bias + embedding[index[query]])
    values = readout @ queried + readout_bias
    return float(values[label] - values[1 - label]), int(np.argmax(values))


def spectral_radius(h, embedding, transition, bias, index):
    z = transition @ h + bias + embedding[index["WAIT"]]
    jac = np.diag(1.0 - np.tanh(z) ** 2) @ transition
    return float(np.max(np.abs(np.linalg.eigvals(jac))))


def analyze_pair(pair, spec, params, index, horizon):
    embedding, transition, bias, readout, readout_bias = params
    h0 = state_after(spec["prefix_0"], embedding, transition, bias, index)
    h1 = state_after(spec["prefix_1"], embedding, transition, bias, index)
    initial_distance = float(np.linalg.norm(h1 - h0))
    rows = []
    state0, state1 = h0, h1
    for step in range(horizon + 1):
        distance = float(np.linalg.norm(state1 - state0))
        margin0, pred0 = query_margin(state0, spec["query"], spec["label_0"], embedding, transition, bias, readout, readout_bias, index)
        margin1, pred1 = query_margin(state1, spec["query"], spec["label_1"], embedding, transition, bias, readout, readout_bias, index)
        rows.append({
            "wait_steps": step,
            "separation": distance,
            "separation_ratio": distance / initial_distance if initial_distance else 0.0,
            "norm_0": float(np.linalg.norm(state0)),
            "norm_1": float(np.linalg.norm(state1)),
            "cosine": cosine(state0, state1),
            "margin_0": margin0,
            "margin_1": margin1,
            "prediction_0": pred0,
            "prediction_1": pred1,
            "jacobian_spectral_radius_0": spectral_radius(state0, embedding, transition, bias, index),
            "jacobian_spectral_radius_1": spectral_radius(state1, embedding, transition, bias, index),
        })
        state0, state1 = wait_step(state0, embedding, transition, bias, index), wait_step(state1, embedding, transition, bias, index)
    final = rows[-1]
    flips = [r["wait_steps"] for r in rows if r["prediction_0"] != spec["label_0"] or r["prediction_1"] != spec["label_1"]]
    deltas = [float(np.linalg.norm(rows[i + 1]["separation"] - rows[i]["separation"])) for i in range(len(rows) - 1)]
    return {
        "pair": pair,
        "initial_separation": initial_distance,
        "final_separation": final["separation"],
        "final_separation_ratio": final["separation_ratio"],
        "minimum_separation_ratio": min(r["separation_ratio"] for r in rows),
        "final_margin_0": final["margin_0"],
        "final_margin_1": final["margin_1"],
        "first_prediction_failure": min(flips) if flips else None,
        "prediction_failure_steps": flips,
        "max_jacobian_spectral_radius": max(max(r["jacobian_spectral_radius_0"], r["jacobian_spectral_radius_1"]) for r in rows),
        "final_state_step_delta": deltas[-1] if deltas else 0.0,
        "trajectory": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01f_config.json")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS.parent / "artifacts/results/gri01f_state_stability_receipt.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-01F config is not frozen")
    parent_path = args.config.with_name(config["parent_config"])
    if digest(parent_path) != config["parent_config_sha256"]:
        raise SystemExit("GRI-01E config hash mismatch")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    base_path = parent_path.with_name(parent["parent_config"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    train = build_examples(base, base["train_delays"])
    theta, solver = solve(train, base["input_alphabet"], config["dimension"], parent["solver"], parent["solver"]["initialization_seed_base"] + config["dimension"])
    embedding, transition, bias, readout, readout_bias = [x.detach().numpy() for x in unpack(theta, len(base["input_alphabet"]), config["dimension"])]
    index = {token: i for i, token in enumerate(base["input_alphabet"])}
    params = (embedding, transition, bias, readout, readout_bias)
    pairs = {name: analyze_pair(name, spec, params, index, config["horizon"]) for name, spec in config["pairs"].items()}
    thresholds = config["thresholds"]
    ratios = [p["final_separation_ratio"] for p in pairs.values()]
    stable = all(p["minimum_separation_ratio"] >= thresholds["stable_min_separation_ratio_min"] and not p["prediction_failure_steps"] for p in pairs.values())
    contractive = all(p["final_separation_ratio"] <= thresholds["collapse_final_separation_ratio_max"] for p in pairs.values())
    unstable = any(p["max_jacobian_spectral_radius"] > thresholds["unstable_growth_ratio_min"] for p in pairs.values())
    if stable:
        verdict = "STABLE_MEMORY"
    elif contractive:
        verdict = "CONTRACTIVE_MEMORY"
    elif unstable:
        verdict = "UNSTABLE_MEMORY"
    else:
        verdict = "TASK_SPECIFIC"
    receipt = {
        "unit": config["unit"], "verdict": verdict,
        "config_sha256": digest(args.config), "parent_gri01e_config_sha256": digest(parent_path),
        "gri01e_parent_config_sha256": digest(base_path), "gri01e_solver": solver,
        "dimension": config["dimension"], "horizon": config["horizon"], "pairs": pairs,
        "explicit_control": {"state_separation": 1.0, "prediction_failures": [], "verdict": "STABLE_MEMORY"},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit": receipt["unit"], "verdict": verdict, "final_separation_ratios": ratios, "first_prediction_failures": {k: v["first_prediction_failure"] for k, v in pairs.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
