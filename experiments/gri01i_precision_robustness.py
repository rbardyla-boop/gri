#!/usr/bin/env python3
"""GRI-01I: finite-precision robustness of the frozen H state trajectories."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

EXPERIMENTS = Path(__file__).resolve().parent
ROOT = EXPERIMENTS.parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import digest  # noqa: E402


TORCH_DTYPES = {
    "float64": torch.float64,
    "float32": torch.float32,
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
}


def signed_metrics(states, labels, weights, bias):
    x = np.asarray(states, dtype=np.float64)
    y = np.where(np.asarray(labels, dtype=np.int64) == 1, 1.0, -1.0)
    w = np.asarray(weights, dtype=np.float64)
    scores = x @ w + float(bias)
    finite = bool(np.isfinite(scores).all())
    if not finite:
        return {
            "finite": False,
            "accuracy": None,
            "minimum_signed_score": None,
            "geometric_margin": None,
        }
    signed = y * scores
    prediction = (scores >= 0.0).astype(np.int64)
    norm = float(np.linalg.norm(w))
    return {
        "finite": True,
        "accuracy": float(np.mean(prediction == (y > 0))),
        "minimum_signed_score": float(np.min(signed)),
        "geometric_margin": float(np.min(signed) / norm) if norm else None,
    }


def dtype_metrics_clean(states, labels, weights, bias, dtype_name):
    dtype = TORCH_DTYPES[dtype_name]
    try:
        x = torch.tensor(states, dtype=dtype)
        w = torch.tensor(weights, dtype=dtype)
        b = torch.tensor(bias, dtype=dtype)
        scores = torch.sum(x * w, dim=1) + b
        scores64 = scores.detach().cpu().to(torch.float64).numpy()
        y = np.where(np.asarray(labels, dtype=np.int64) == 1, 1.0, -1.0)
        finite = bool(torch.isfinite(scores).all().item())
        if not finite:
            return {
                "storage_dtype": dtype_name,
                "finite": False,
                "accuracy": None,
                "minimum_signed_score": None,
                "geometric_margin": None,
            }
        effective_w = w.detach().cpu().to(torch.float64).numpy()
        signed = y * scores64
        return {
            "storage_dtype": dtype_name,
            "finite": True,
            "accuracy": float(np.mean((scores64 >= 0.0).astype(np.int64) == np.asarray(labels))),
            "minimum_signed_score": float(np.min(signed)),
            "geometric_margin": float(np.min(signed) / np.linalg.norm(effective_w)) if np.linalg.norm(effective_w) else None,
        }
    except (RuntimeError, TypeError, ValueError, OverflowError) as error:
        return {
            "storage_dtype": dtype_name,
            "finite": False,
            "accuracy": None,
            "minimum_signed_score": None,
            "geometric_margin": None,
            "error": str(error),
        }


def quantize_state(states, bits):
    levels = (2 ** (bits - 1)) - 1
    scale = 1.0 / levels
    values = np.asarray(states, dtype=np.float64)
    return np.clip(np.rint(values / scale), -levels, levels) * scale


def quantized_metrics(states, labels, weights, bias, bits):
    quantized = quantize_state(states, bits)
    result = signed_metrics(quantized, labels, weights, bias)
    result["storage_quantization"] = f"symmetric_uniform_{bits}bit"
    result["quantization_scale"] = 1.0 / ((2 ** (bits - 1)) - 1)
    return result


def task_classification(task_result, config):
    reference_last = task_result["representations"][config["reference_representation"]]["last_usable_wait"]
    statuses = task_result["representations"]
    losses = [
        status["last_usable_wait"] is not None and reference_last is not None and status["last_usable_wait"] < reference_last
        or status["last_usable_wait"] is None and reference_last is not None
        for name, status in statuses.items() if name != config["reference_representation"]
    ]
    modest_last = [statuses[name]["last_usable_wait"] for name in config["modest_representations"]]
    immediate = all(value is None or value <= config["immediate_loss_wait_max"] for value in modest_last)
    if immediate:
        return "IMMEDIATE_LOSS"
    if reference_last is not None and not any(losses):
        return "ROBUST_STATE"
    if reference_last is not None and any(losses):
        return "PRECISION_FRAGILE"
    return "IMMEDIATE_LOSS"


def overall_classification(classifications):
    values = set(classifications.values())
    return next(iter(values)) if len(values) == 1 else "TASK_SPECIFIC"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01i_config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri01i_precision_robustness_receipt.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-01I config is not frozen")
    parent_config_path = args.config.with_name(config["parent_config"])
    if digest(parent_config_path) != config["parent_config_sha256"]:
        raise SystemExit("GRI-01H config hash mismatch")
    receipt_path = args.config.parent / config["parent_receipt"]
    if digest(receipt_path) != config["parent_receipt_sha256"]:
        raise SystemExit("GRI-01H receipt hash mismatch")
    parent_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    horizon = int(parent_receipt["horizon"])
    results = {}
    for task, task_data in parent_receipt["tasks"].items():
        task_cases = [case for case in parent_receipt["states"] if case["task"] == task]
        labels_by_wait = {
            wait: [case["label"] for case in task_cases]
            for wait in range(horizon + 1)
        }
        rows_by_representation = {}
        rep_names = [f"dtype_{name}" for name in config["dtype_representations"]] + [f"quantized_{bits}" for bits in config["fixed_point_bits"]]
        for representation in rep_names:
            rows_by_representation[representation] = []
        for wait in range(horizon + 1):
            states = [case["states"][wait] for case in task_cases]
            separator = task_data["wait_specific_separators"][str(wait)]
            for representation in rep_names:
                if not separator.get("separator_found"):
                    row = {"wait_steps": wait, "exact_separator": False, "usable": False, "reason": "no_exact_H_separator"}
                else:
                    weights = separator["weights"]
                    bias = separator["bias"]
                    if representation.startswith("dtype_"):
                        name = representation.removeprefix("dtype_")
                        metrics = dtype_metrics_clean(states, labels_by_wait[wait], weights, bias, name)
                    else:
                        bits = int(representation.removeprefix("quantized_"))
                        metrics = quantized_metrics(states, labels_by_wait[wait], weights, bias, bits)
                    row = {
                        "wait_steps": wait,
                        "exact_separator": True,
                        "usable": bool(
                            metrics.get("finite")
                            and metrics.get("accuracy") == 1.0
                            and metrics.get("geometric_margin") is not None
                            and metrics.get("geometric_margin") > 0.0
                        ),
                        **metrics,
                    }
                rows_by_representation[representation].append(row)
        representations = {}
        for name, rows in rows_by_representation.items():
            usable_waits = [row["wait_steps"] for row in rows if row["usable"]]
            representations[name] = {
                "usable_waits": usable_waits,
                "last_usable_wait": max(usable_waits) if usable_waits else None,
                "rows": rows,
            }
        task_result = {
            "H_classification": task_data["classification"],
            "representations": representations,
        }
        task_result["exact_H_last_usable_wait"] = representations[config["reference_representation"]]["last_usable_wait"]
        task_result["classification"] = task_classification(task_result, config)
        results[task] = task_result

    classifications = {task: result["classification"] for task, result in results.items()}
    receipt = {
        "unit": config["unit"],
        "verdict": overall_classification(classifications),
        "parent_H_config_sha256": digest(parent_config_path),
        "parent_H_receipt_sha256": digest(receipt_path),
        "implementation_sha256": digest(Path(__file__)),
        "reference_representation": config["reference_representation"],
        "dtype_representations": config["dtype_representations"],
        "fixed_point_bits": config["fixed_point_bits"],
        "classification_rules": config["classification"],
        "tasks": results,
        "task_classifications": classifications,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": receipt["unit"],
        "verdict": receipt["verdict"],
        "task_classifications": classifications,
        "last_usable_waits": {
            task: {name: value["last_usable_wait"] for name, value in result["representations"].items()}
            for task, result in results.items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
