"""Exact Schlögl active-latch baseline for the LCB failure map.

This is a prior-art/null model, not a candidate breakthrough.

Reaction benchmark (A and B chemostatted):
    A + 2X -> 3X
    3X -> A + 2X
    X -> B
    B -> X

The stochastic propensity convention is the common Schlögl benchmark:
    k1 = 3e-7, A = 1e5
    k2 = 1e-4
    k3 = 3.5
    k4 = 1e-3, B = 2e5 nominally

The script computes the birth-death stationary distribution exactly by recursion,
channel-resolved steady-state entropy production for the two reversible reaction
pairs, and mean first-passage times from each probability mode to the basin
separator using a tridiagonal solve.

No physical Joule value is claimed. Entropy production is reported in k_B per
model-time unit for the Markov jump model.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

A = 100_000.0
K1 = 3e-7
K2 = 1e-4
K3 = 3.5
K4 = 1e-3
NMAX = 1200


def propensities(B: float, nmax: int = NMAX):
    w1, w2, w3, w4, birth, death = [], [], [], [], [], []
    for n in range(nmax + 1):
        # Standard stochastic mass-action combinatorial convention.
        r1 = K1 * A * n * (n - 1) / 2.0
        r2 = K2 * n * (n - 1) * (n - 2) / 6.0
        r3 = K3 * n
        r4 = K4 * B
        w1.append(r1)
        w2.append(r2)
        w3.append(r3)
        w4.append(r4)
        birth.append(r1 + r4)
        death.append(r2 + r3)
    return w1, w2, w3, w4, birth, death


def stationary(B: float, nmax: int = NMAX):
    rates = propensities(B, nmax)
    *_, birth, death = rates
    logp = [float("-inf")] * (nmax + 1)
    logp[0] = 0.0
    for n in range(nmax):
        logp[n + 1] = logp[n] + math.log(birth[n]) - math.log(death[n + 1])
    offset = max(logp)
    p = [math.exp(x - offset) for x in logp]
    z = sum(p)
    p = [x / z for x in p]
    modes = [
        i
        for i in range(1, nmax)
        if p[i] >= p[i - 1] and p[i] >= p[i + 1] and p[i] > 1e-14
    ]
    return p, modes, rates


def split_info(B: float):
    p, modes, rates = stationary(B)
    if len(modes) < 2:
        return None
    low, high = modes[0], modes[-1]
    separator = min(range(low + 1, high), key=lambda i: p[i])
    low_mass = sum(p[: separator + 1])
    return low_mass, low, high, separator, p, rates


def balanced_B(lo: float = 190_000.0, hi: float = 205_000.0) -> float:
    """Find the chemostat B giving equal stationary basin masses."""
    for _ in range(60):
        mid = (lo + hi) / 2.0
        info = split_info(mid)
        if info is None:
            raise RuntimeError("balanced-B bracket left the bistable region")
        if info[0] > 0.5:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def channel_resolved_epr(p, rates) -> float:
    """Schnakenberg-style steady EPR for the two explicit reverse channel pairs."""
    w1, w2, w3, w4, _, _ = rates
    total = 0.0
    for n in range(len(p) - 1):
        # Pair 1: A+2X -> 3X and its reverse.
        # Pair 2: B -> X and X -> B.
        for forward, reverse in ((w1[n], w2[n + 1]), (w4[n], w3[n + 1])):
            a = p[n] * forward
            b = p[n + 1] * reverse
            if a > 0.0 and b > 0.0:
                total += (a - b) * math.log(a / b)
    return total


def solve_tridiagonal(lower, diagonal, upper, rhs):
    """Thomas algorithm."""
    lower = list(lower)
    diagonal = list(diagonal)
    upper = list(upper)
    rhs = list(rhs)
    n = len(diagonal)
    for i in range(1, n):
        factor = lower[i - 1] / diagonal[i - 1]
        diagonal[i] -= factor * upper[i - 1]
        rhs[i] -= factor * rhs[i - 1]
    result = [0.0] * n
    result[-1] = rhs[-1] / diagonal[-1]
    for i in range(n - 2, -1, -1):
        result[i] = (rhs[i] - upper[i] * result[i + 1]) / diagonal[i]
    return result


def mfpt(rates, start: int, target: int, upper_bound: int = NMAX) -> float:
    """Mean first-passage time to the basin separator."""
    *_, birth, death = rates
    if start < target:
        states = list(range(target))
        diagonal = [-(birth[s] + death[s]) for s in states]
        upper = [birth[s] for s in states[:-1]]
        lower = [death[s] for s in states[1:]]
        solution = solve_tridiagonal(lower, diagonal, upper, [-1.0] * len(states))
        return solution[start]

    states = list(range(target + 1, upper_bound + 1))
    diagonal = []
    upper = []
    lower = []
    for j, s in enumerate(states):
        effective_birth = birth[s] if s < upper_bound else 0.0
        diagonal.append(-(effective_birth + death[s]))
        if j < len(states) - 1:
            upper.append(birth[s])
        if j > 0:
            lower.append(death[s])
    solution = solve_tridiagonal(lower, diagonal, upper, [-1.0] * len(states))
    return solution[start - (target + 1)]


def point_report(B: float) -> dict:
    info = split_info(B)
    if info is None:
        raise RuntimeError(f"B={B} is not bimodal under this truncation")
    low_mass, low, high, separator, p, rates = info
    epr = channel_resolved_epr(p, rates)
    # With the benchmark combinatorial convention, the edge-cycle affinity is constant.
    affinity = math.log((3.0 * K1 * A * K3) / (K2 * K4 * B))
    return {
        "B": B,
        "low_mode": low,
        "high_mode": high,
        "separator": separator,
        "low_basin_mass": low_mass,
        "high_basin_mass": 1.0 - low_mass,
        "dimensionless_cycle_affinity": affinity,
        "channel_resolved_epr_kB_per_time": epr,
        "cycle_flux_from_epr_over_affinity": epr / affinity,
        "mfpt_low_to_separator": mfpt(rates, low, separator),
        "mfpt_high_to_separator": mfpt(rates, high, separator),
    }


def build_report() -> dict:
    b_balanced = balanced_B()
    # Chemical detailed balance for this propensity convention.
    b_detailed_balance = (3.0 * K1 * A * K3) / (K2 * K4)
    p_eq, _, rates_eq = stationary(b_detailed_balance, nmax=1600)
    epr_eq = channel_resolved_epr(p_eq, rates_eq)
    result = {
        "schema_version": 1,
        "purpose": "thermodynamically explicit active fixed-point baseline; not novelty",
        "reaction_scheme": [
            "A + 2X -> 3X",
            "3X -> A + 2X",
            "X -> B",
            "B -> X",
        ],
        "parameters": {
            "A": A,
            "k1": K1,
            "k2": K2,
            "k3": K3,
            "k4": K4,
            "state_truncation": NMAX,
        },
        "canonical_benchmark_B_200000": point_report(200_000.0),
        "balanced_B": b_balanced,
        "balanced_binary_point": point_report(b_balanced),
        "chemical_detailed_balance_B": b_detailed_balance,
        "epr_at_detailed_balance_numerical": epr_eq,
        "interpretation": {
            "bistability": "powered nonequilibrium fixed-point memory baseline",
            "entropy_production": "channel-resolved continuous-time Markov jump entropy production in k_B per model time",
            "energy_withdrawal": "literature establishes bistability requires nonequilibrium chemostatting; a closed detailed-balanced system has unique equilibrium",
            "claim_boundary": "does not establish a hardware energy advantage or a new primitive",
        },
    }
    # Fail closed if the baseline ceases to reproduce the intended qualitative facts.
    assert abs(result["balanced_binary_point"]["low_basin_mass"] - 0.5) < 1e-9
    assert result["balanced_binary_point"]["channel_resolved_epr_kB_per_time"] > 0.0
    assert result["balanced_binary_point"]["mfpt_low_to_separator"] > 0.0
    assert result["balanced_binary_point"]["mfpt_high_to_separator"] > 0.0
    assert result["epr_at_detailed_balance_numerical"] < 1e-12
    return result


def main() -> None:
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
