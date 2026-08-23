#!/usr/bin/env python3
"""Explicit finite-state control for the GRI-01 recurrence fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import build_examples, canonical, digest  # noqa: E402


class FiniteStateTransducer:
    """Small explicit control: prefix registers, no learned parameters."""

    def __init__(self, state=None):
        self.state = state or {"memory": None, "first": None, "second": None, "last_output": None}

    def step(self, token):
        if token in ("BIT_0", "BIT_1"):
            self.state["memory"] = int(token == "BIT_1")
        elif token in ("A", "B"):
            if self.state["first"] is None:
                self.state["first"] = token
            elif self.state["second"] is None:
                self.state["second"] = token
            self.state["memory"] = int(token == "B")
        elif token == "QUERY_DELAY" or token == "QUERY_CORRECTION":
            self.state["last_output"] = self.state["memory"]
        elif token == "QUERY_ORDER":
            self.state["last_output"] = int((self.state["first"], self.state["second"]) == ("B", "A"))
        return self.state["last_output"]

    def run(self, tokens):
        for token in tokens:
            self.step(token)
        return self.state["last_output"]

    def serialize(self):
        return canonical(self.state)

    @classmethod
    def deserialize(cls, payload):
        state = json.loads(payload.decode("utf-8"))
        if set(state) != {"memory", "first", "second", "last_output"}:
            raise ValueError("unexpected serialized state shape")
        return cls(state)


def check_examples(examples):
    cells = defaultdict(lambda: {"correct": 0, "total": 0})
    failures = []
    restart_cases = 0
    for task, tokens, expected, delay in examples:
        full = FiniteStateTransducer().run(tokens)
        key = (task, delay)
        cells[key]["total"] += 1
        if full == expected:
            cells[key]["correct"] += 1
        else:
            failures.append({"task": task, "delay": delay, "tokens": tokens, "expected": expected, "observed": full})
        for split in range(len(tokens) + 1):
            uninterrupted = FiniteStateTransducer().run(tokens)
            left = FiniteStateTransducer()
            left.run(tokens[:split])
            right = FiniteStateTransducer.deserialize(left.serialize())
            resumed = right.run(tokens[split:])
            restart_cases += 1
            if uninterrupted != resumed:
                failures.append({"task": task, "delay": delay, "split": split, "kind": "serialize_restart", "expected": uninterrupted, "observed": resumed})
    rows = []
    for (task, delay), cell in sorted(cells.items()):
        rows.append({"task": task, "delay": delay, "correct": cell["correct"], "total": cell["total"], "accuracy": cell["correct"] / cell["total"]})
    return rows, failures, restart_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri01_recurrence_config.json")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS.parent / "artifacts/results/gri01d_finite_state_receipt.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("config is not frozen")
    alphabet = config["input_alphabet"]
    train = build_examples(config, config["train_delays"])
    test = build_examples(config, config["test_delays"])
    train_rows, train_failures, train_restart = check_examples(train)
    test_rows, test_failures, test_restart = check_examples(test)
    failures = train_failures + test_failures
    receipt = {
        "unit": "GRI-01D-MINIMAL-EXPLICIT-STATE-CONTROL",
        "verdict": "CONTROL_PASS" if not failures else "CONTROL_FAIL",
        "config_sha256": digest(args.config),
        "implementation_sha256": digest(Path(__file__)),
        "train_fixture_sha256": hashlib.sha256(canonical({"alphabet": alphabet, "examples": train})).hexdigest(),
        "test_fixture_sha256": hashlib.sha256(canonical({"alphabet": alphabet, "examples": test})).hexdigest(),
        "state_representation": "memory, first, second, last_output; explicit finite registers; no learned parameters",
        "train": {"cells": train_rows, "restart_cases": train_restart, "failures": train_failures},
        "test": {"cells": test_rows, "restart_cases": test_restart, "failures": test_failures},
        "serialization": {"status": "PASS" if not failures else "FAIL", "byte_stable": not bool(failures)},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(receipt))
    print(json.dumps(receipt, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
