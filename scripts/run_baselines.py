#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.baseline import WeightTiedGraphReasoner
from gri_models.data import load_examples
from gri_models.geometric import SO4GeometricReasoner
from gri_models.train import accuracy, set_seed, train_model


def evaluate_depths(model, artifact_dir: Path):
    out = {}
    for depth in (5, 8, 16, 32, 64):
        examples = load_examples(artifact_dir / f"test_depth_{depth}.jsonl")
        out[str(depth)] = accuracy(model, examples, steps=depth)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/frozen/world0_v0_1")
    ap.add_argument("--model", choices=("baseline", "geometric"), default="baseline")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    torch.set_num_threads(1)
    train = load_examples(args.artifact_dir / "train.jsonl")
    val = load_examples(args.artifact_dir / "validation.jsonl")
    set_seed(args.seed)
    model = WeightTiedGraphReasoner() if args.model == "baseline" else SO4GeometricReasoner()
    result = train_model(model, train, epochs=args.epochs, steps=4, seed=args.seed)
    report = {
        "model": args.model,
        "seed": args.seed,
        "epochs": args.epochs,
        "parameters": sum(p.numel() for p in model.parameters()),
        "final_loss": result.final_loss,
        "train_accuracy": result.train_accuracy,
        "validation_accuracy_t4": accuracy(model, val, steps=4),
        "extrapolation": evaluate_depths(model, args.artifact_dir),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
