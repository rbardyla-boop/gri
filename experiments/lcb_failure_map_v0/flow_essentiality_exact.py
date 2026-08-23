"""Exact finite-state current-ablation diagnostic for FET-0.

Uses a six-state ring with two high-probability wells. A divergence-free steady
current is added while the stationary distribution and each state's total escape
rate remain unchanged. Additive reversibilization removes the current exactly.

This is a counterexample/diagnostic, not a new mathematical result.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

PI = [0.35, 0.075, 0.075, 0.35, 0.075, 0.075]
SYMMETRIC_EDGE_TRAFFIC = 0.02
CURRENTS = [0.0, 0.002, 0.005, 0.01, 0.015, 0.019]


def ring_generator(current: float):
    n = len(PI)
    q = [[0.0] * n for _ in range(n)]
    for i in range(n):
        j = (i + 1) % n
        q[i][j] += (SYMMETRIC_EDGE_TRAFFIC + current) / PI[i]
        q[j][i] += (SYMMETRIC_EDGE_TRAFFIC - current) / PI[j]
    for i in range(n):
        q[i][i] = -sum(q[i])
    return q


def time_reverse(q):
    n = len(PI)
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                out[i][j] = PI[j] * q[j][i] / PI[i]
        out[i][i] = -sum(out[i])
    return out


def average(a, b):
    return [[(a[i][j] + b[i][j]) / 2.0 for j in range(len(a))] for i in range(len(a))]


def max_abs_delta(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(len(a)) for j in range(len(a)))


def stationarity_error(q):
    return max(abs(sum(PI[i] * q[i][j] for i in range(len(PI)))) for j in range(len(PI)))


def entropy_production(q):
    total = 0.0
    for i in range(len(PI)):
        for j in range(i + 1, len(PI)):
            forward = PI[i] * q[i][j]
            reverse = PI[j] * q[j][i]
            if forward > 0.0 and reverse > 0.0:
                total += (forward - reverse) * math.log(forward / reverse)
    return total


def solve_dense(a, b):
    """Small Gaussian-elimination solver to keep this diagnostic dependency-free."""
    a = [row[:] for row in a]
    b = list(b)
    n = len(b)
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        denom = a[col][col]
        if abs(denom) < 1e-15:
            raise ValueError("singular linear system")
        for row in range(col + 1, n):
            factor = a[row][col] / denom
            for k in range(col, n):
                a[row][k] -= factor * a[col][k]
            b[row] -= factor * b[col]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (b[i] - sum(a[i][j] * x[j] for j in range(i + 1, n))) / a[i][i]
    return x


def mfpt_to_set(q, start: int, targets: set[int]):
    states = [i for i in range(len(q)) if i not in targets]
    index = {state: i for i, state in enumerate(states)}
    sub = [[q[i][j] for j in states] for i in states]
    times = solve_dense(sub, [-1.0] * len(states))
    return times[index[start]]


def build_report():
    reversible_reference = ring_generator(0.0)
    rows = []
    for current in CURRENTS:
        q = ring_generator(current)
        q_rev = average(q, time_reverse(q))
        row = {
            "current_j": current,
            "stationarity_max_abs": stationarity_error(q),
            "epr": entropy_production(q),
            "mfpt_to_other_macrostate": mfpt_to_set(q, 0, {2, 3, 4}),
            "reversibilized_mfpt": mfpt_to_set(q_rev, 0, {2, 3, 4}),
            "reversibilized_delta_from_j0": max_abs_delta(q_rev, reversible_reference),
            "diagonal_delta_after_reversibilization": max(
                abs(q[i][i] - q_rev[i][i]) for i in range(len(PI))
            ),
        }
        assert row["stationarity_max_abs"] < 1e-12
        assert row["reversibilized_delta_from_j0"] < 1e-12
        assert row["diagonal_delta_after_reversibilization"] < 1e-12
        rows.append(row)

    return {
        "schema_version": 1,
        "purpose": "exact finite-state flow ablation diagnostic",
        "pi": PI,
        "symmetric_edge_traffic": SYMMETRIC_EDGE_TRAFFIC,
        "target_macrostate": [2, 3, 4],
        "rows": rows,
        "finding": "same stationary distribution and state escape rates; increasing circulation raises EPR and reduces this retention MFPT",
        "claim_boundary": "counterexample only; not a theorem that irreversible currents always harm memory",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = build_report()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
