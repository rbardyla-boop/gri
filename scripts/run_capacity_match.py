#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.data import load_examples
from gri_models.train import accuracy, train_model
from gri_models.gri05 import DEPTHS, PARAMETERS, PRIMARY_DEPTHS, SEEDS, build_model, primary_metric

def evaluate_depths(model, artifact_dir: Path) -> dict[str, float]:
    return {
        str(depth): accuracy(model, load_examples(artifact_dir / f"test_depth_{depth}.jsonl"), steps=depth)
        for depth in DEPTHS
    }


def run_one(kind: str, seed: int, artifact_dir: Path) -> dict:
    torch.set_num_threads(1)
    train = load_examples(artifact_dir / "train.jsonl")
    val = load_examples(artifact_dir / "validation.jsonl")
    model = build_model(kind, seed)
    started = time.perf_counter()
    result = train_model(
        model,
        train,
        epochs=80,
        steps=4,
        learning_rate=3e-3,
        seed=seed,
        batch_size=16,
    )
    extrapolation = evaluate_depths(model, artifact_dir)
    return {
        "model": kind,
        "seed": seed,
        "epochs": 80,
        "train_steps": 4,
        "batch_size": 16,
        "optimizer": "AdamW",
        "learning_rate": 3e-3,
        "weight_decay": 1e-4,
        "gradient_clip": 1.0,
        "parameters": PARAMETERS,
        "final_loss": result.final_loss,
        "train_accuracy": result.train_accuracy,
        "validation_accuracy_t4": accuracy(model, val, steps=4),
        "extrapolation": extrapolation,
        "primary_metric": primary_metric(extrapolation),
        "elapsed_seconds": time.perf_counter() - started,
    }


def summarize(results: list[dict]) -> dict:
    by_model = {}
    for kind in ("baseline", "so4"):
        rows = [r for r in results if r["model"] == kind]
        if not rows:
            continue
        p = [r["primary_metric"] for r in rows]
        by_model[kind] = {
            "n": len(rows),
            "mean_train_accuracy": statistics.mean(r["train_accuracy"] for r in rows),
            "mean_validation_accuracy_t4": statistics.mean(r["validation_accuracy_t4"] for r in rows),
            "mean_primary_metric": statistics.mean(p),
            "stdev_primary_metric": statistics.stdev(p) if len(p) > 1 else 0.0,
        }
    return by_model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/frozen/world0_v0_1")
    ap.add_argument("--model", choices=("baseline", "so4"))
    ap.add_argument("--seed", type=int, choices=SEEDS)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if (args.model is None) != (args.seed is None):
        ap.error("--model and --seed must be supplied together")

    if args.model:
        result = run_one(args.model, args.seed, args.artifact_dir)
        text = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0

    results = [run_one(kind, seed, args.artifact_dir) for kind in ("baseline", "so4") for seed in SEEDS]
    report = {"results": results, "summary": summarize(results)}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
