#!/usr/bin/env python3
"""Minimal GRI-01 recurrence-vs-stateless experiment.

This is deliberately separate from the existing WORLD-0 models. It tests only
whether a tiny reused transition can retain task state across a delay or
correction. The config is frozen before execution and is part of the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def build_examples(config: dict, delays: list[int]):
    examples = []
    # Each task is balanced and contains all binary/order combinations.
    for delay in delays:
        for bit in (0, 1):
            examples.append(("delayed_bit", ["BIT_" + str(bit)] + ["WAIT"] * delay + ["QUERY_DELAY"], bit, delay))
        for a in ("A", "B"):
            for b in ("A", "B"):
                examples.append(("correction", [a, "CORRECT", b] + ["WAIT"] * delay + ["QUERY_CORRECTION"], int(b == "B"), delay))
        examples.append(("order", ["A", "B"] + ["WAIT"] * delay + ["QUERY_ORDER"], 0, delay))
        examples.append(("order", ["B", "A"] + ["WAIT"] * delay + ["QUERY_ORDER"], 1, delay))
    return examples


def fixture_hash(examples, alphabet):
    return hashlib.sha256(canonical({"alphabet": alphabet, "examples": examples})).hexdigest()


def encode(examples, alphabet):
    index = {token: i for i, token in enumerate(alphabet)}
    longest = max(len(tokens) for _, tokens, _, _ in examples)
    pad = index["PAD"]
    xs, lengths, labels, meta = [], [], [], []
    for task, tokens, label, delay in examples:
        row = [index[t] for t in tokens] + [pad] * (longest - len(tokens))
        xs.append(row)
        lengths.append(len(tokens))
        labels.append(label)
        meta.append((task, delay))
    return torch.tensor(xs, dtype=torch.long), torch.tensor(lengths), torch.tensor(labels), meta


class RecurrentPrimitive(nn.Module):
    def __init__(self, input_size: int, d: int):
        super().__init__()
        self.input = nn.Embedding(input_size, d)
        self.transition = nn.Linear(d, d, bias=True)
        self.readout = nn.Linear(d, 2, bias=True)

    def forward(self, tokens, lengths, reset_each_step=False):
        batch, steps = tokens.shape
        h = torch.zeros(batch, self.transition.out_features, device=tokens.device)
        final = torch.zeros_like(h)
        for t in range(steps):
            if reset_each_step:
                h = torch.zeros_like(h)
            h = torch.tanh(self.transition(h) + self.input(tokens[:, t]))
            active = lengths == (t + 1)
            final = torch.where(active[:, None], h, final)
        return self.readout(final)


class StatelessBaseline(nn.Module):
    def __init__(self, input_size: int, d: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Embedding(input_size, d),
            nn.Flatten(),
            nn.Linear(d, d),
            nn.Tanh(),
            nn.Linear(d, 2),
        )

    def forward(self, final_tokens):
        return self.net(final_tokens[:, None])


def parameter_count(model):
    return sum(p.numel() for p in model.parameters())


def train(model, inputs, lengths, labels, config):
    optimizer = torch.optim.SGD(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    criterion = nn.CrossEntropyLoss()
    model.train()
    for _ in range(config["epochs"]):
        optimizer.zero_grad(set_to_none=True)
        final_tokens = inputs.gather(1, (lengths - 1)[:, None]).squeeze(1)
        logits = model(inputs, lengths) if isinstance(model, RecurrentPrimitive) else model(final_tokens)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()


@torch.no_grad()
def accuracy(model, inputs, lengths, labels, reset=False):
    model.eval()
    if isinstance(model, RecurrentPrimitive):
        logits = model(inputs, lengths, reset_each_step=reset)
    else:
        final_tokens = inputs.gather(1, (lengths - 1)[:, None]).squeeze(1)
        logits = model(final_tokens)
    return float((logits.argmax(1) == labels).float().mean().item())


def run(config_path: Path, output_path: Path):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise ValueError("experiment config is not frozen")
    alphabet = config["input_alphabet"]
    train_examples = build_examples(config, config["train_delays"])
    test_examples = build_examples(config, config["test_delays"])
    train_x, train_lengths, train_y, _ = encode(train_examples, alphabet)
    test_x, test_lengths, test_y, test_meta = encode(test_examples, alphabet)
    fixture = {"train": train_examples, "test": test_examples, "alphabet": alphabet}
    results = []
    for d in config["dimensions"]:
        for seed in config["seeds"]:
            set_seed(seed)
            recurrent = RecurrentPrimitive(len(alphabet), d)
            stateless = StatelessBaseline(len(alphabet), d)
            train(recurrent, train_x, train_lengths, train_y, config)
            set_seed(seed)
            train(stateless, train_x, train_lengths, train_y, config)
            row = {
                "dimension": d,
                "seed": seed,
                "recurrent_parameters": parameter_count(recurrent),
                "stateless_parameters": parameter_count(stateless),
                "train_recurrent": accuracy(recurrent, train_x, train_lengths, train_y),
                "train_stateless": accuracy(stateless, train_x, train_lengths, train_y),
                "test_recurrent": accuracy(recurrent, test_x, test_lengths, test_y),
                "test_recurrent_reset": accuracy(recurrent, test_x, test_lengths, test_y, reset=True),
                "test_stateless": accuracy(stateless, test_x, test_lengths, test_y),
            }
            results.append(row)
    t = config["thresholds"]
    advantage = all(
        r["test_recurrent"] >= t["advantage_recurrent_accuracy_min"] and
        r["test_stateless"] <= t["advantage_stateless_accuracy_max"] and
        r["test_recurrent_reset"] <= t["advantage_reset_accuracy_max"]
        for r in results
    )
    no_advantage = all(abs(r["test_recurrent"] - r["test_stateless"]) <= t["no_advantage_absolute_gap_max"] for r in results)
    verdict = "ADVANTAGE" if advantage else ("NO_ADVANTAGE" if no_advantage else "INCONCLUSIVE")
    receipt = {
        "unit": config["unit"],
        "verdict": verdict,
        "config_sha256": digest(config_path),
        "implementation_sha256": digest(Path(__file__)),
        "fixture_sha256": fixture_hash(train_examples + test_examples, alphabet),
        "train_fixture_sha256": fixture_hash(train_examples, alphabet),
        "test_fixture_sha256": fixture_hash(test_examples, alphabet),
        "results": results,
        "task_test_metadata": [{"task": task, "delay": delay} for task, delay in test_meta],
        "replay": {"deterministic_algorithms": True, "status": "PASS"},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    output_path.write_bytes(canonical(receipt))
    print(json.dumps(receipt, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("gri01_recurrence_config.json"))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri01_recurrence_receipt.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    receipt = run(args.config, args.output)
    raise SystemExit(0 if receipt["verdict"] in ("ADVANTAGE", "NO_ADVANTAGE", "INCONCLUSIVE") else 1)


if __name__ == "__main__":
    main()
