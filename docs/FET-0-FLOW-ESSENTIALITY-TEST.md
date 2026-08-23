# FET-0 — Flow-Essentiality Test

## Status

```text
UNIT:                  FET-0
PURPOSE:               MECHANISM-CREDIT / KILL TEST
NEW MATHEMATICS:       NO
CANDIDATE ADVANTAGE:   NOT ESTABLISHED
```

FET-0 asks a narrower question than the historical Energy Withdrawal Test:

> Does the **irreversible steady flow itself** deserve credit for the claimed memory property, or is the same property already explained by the stationary landscape / barriers / ordinary attractor stability?

## Why the old test is insufficient

The failure map constructed a powered fixed-point latch that:

- has two states under one powered operating point;
- accepts finite write pulses;
- relaxes back after bounded perturbations;
- retains after the pulse ends;
- loses its state when power is removed.

Therefore `state disappears when power is removed` does not isolate a limit-cycle, circulation, or LCB-specific mechanism.

## Exact current ablation for a finite Markov process

Let `Q` be an irreducible continuous-time Markov generator with stationary distribution `pi`.

The time-reversed generator is

```text
Q*_{ij} = pi_j Q_{ji} / pi_i,   i != j
```

with diagonal entries chosen so each row sums to zero.

Define the additive reversibilization

```text
Q_rev = (Q + Q*) / 2.
```

This is a standard reversibilization construction, not an LCB invention.

It gives a useful mechanism control because:

1. `Q_rev` has the **same stationary distribution** `pi`;
2. `Q_rev` satisfies detailed balance, so its steady probability currents are zero;
3. because `Q*_{ii}=Q_{ii}`, `Q_rev` preserves the original per-state total escape rate;
4. the antisymmetric/current-carrying part of the dynamics is removed.

Equivalently, if stationary edge flows are

```text
F_ij = pi_i Q_ij,
```

then the control uses the symmetric traffic

```text
S_ij = (F_ij + F_ji)/2
Q_rev,ij = S_ij / pi_i.
```

## Mechanism-credit rule

For a memory metric `M`:

```text
candidate:          M(Q)
current-ablated:    M(Q_rev)
```

Interpretation:

- if `M(Q) ~= M(Q_rev)`, steady current is **unnecessary** for that metric;
- if `M(Q) < M(Q_rev)`, current **harms** that metric;
- if `M(Q) > M(Q_rev)`, current is a **candidate contributing mechanism**, but not yet sufficient for an advantage claim.

A positive difference still must survive matched physical baselines, cost accounting, perturbation tests, and prior art.

## Exact six-state diagnostic

A six-state ring was constructed with stationary distribution

```text
pi = [0.35, 0.075, 0.075, 0.35, 0.075, 0.075]
```

so states 0 and 3 are two probability wells.

Each undirected ring edge has symmetric stationary traffic `s=0.02`. A divergence-free clockwise current `j` is introduced through

```text
F_clockwise     = s + j
F_counterclock  = s - j
0 <= j < s.
```

The stationary distribution and each state's total escape rate are unchanged as `j` changes. The additive reversibilization of every member of this family is exactly the `j=0` process.

Starting at state 0, define loss of the stored macrostate as first entry into `{2,3,4}`.

| current j | entropy production | MFPT to other macrostate | reversibilized MFPT |
|---:|---:|---:|---:|
| 0.000 | 0.0000 | 21.2500 | 21.2500 |
| 0.002 | 0.0048 | 21.0396 | 21.2500 |
| 0.005 | 0.0306 | 20.0000 | 21.2500 |
| 0.010 | 0.1318 | 17.0000 | 21.2500 |
| 0.015 | 0.3503 | 13.6000 | 21.2500 |
| 0.019 | 0.8353 | 11.1695 | 21.2500 |

This exact finite-state example has no integration timestep and no Monte Carlo error.

It demonstrates two things:

1. irreversible current can alter memory kinetics even while the stationary distribution and local escape-rate budget are held fixed;
2. in this example, more dissipation makes retention **worse**, not better.

This is not a theorem that currents always harm memory. It is a counterexample to the claim that current/dissipation is inherently persistence-enhancing.

## FET-0 pass conditions for a future candidate

A future candidate gets **flow mechanism credit** only if:

1. the relevant state distribution / quasipotential is measured or calculable;
2. a current-ablated control is constructed without changing the claimed static landscape variables, or the impossibility of doing so is itself rigorously demonstrated;
3. the candidate improves a preregistered memory metric over that control;
4. the improvement survives matched state priors, noise, readout, write target, and observation time;
5. the gain is not reproduced by an ordinary static-barrier change at the same physical power/error/latency budget;
6. a physically realizable comparator is also tested, because additive reversibilization is a mathematical mechanism control and need not correspond to the same hardware/reaction topology;
7. the result survives a parametron and a thermodynamically consistent active fixed-point baseline.

## Required metrics

At minimum:

```text
retention / first-passage error
perturbation recovery
write success
write latency
read error / latency
reset latency
maintenance power or entropy production
write/read/reset work
bias / mismatch sensitivity
```

Do not compress these into one IPE-style scalar until the individual quantities are physically calibrated.

## Prior-art note

Additive reversibilization is standard Markov-chain theory: averaging a chain with its time reversal creates a reversible chain with the same stationary distribution. FET-0's potential contribution is only methodological: using that standard construction as a **mechanism ablation** inside the Gauntlet research discipline.

## Terminal interpretation

```text
ENERGY WITHDRAWAL ALONE:       INSUFFICIENT
DISSIPATION ALONE:             INSUFFICIENT
STEADY CURRENT ALONE:          INSUFFICIENT
CURRENT CAN ALTER KINETICS:    YES
CURRENT IMPROVES MEMORY:       NOT GENERALLY
FLOW-ESSENTIAL ADVANTAGE:      NOT ESTABLISHED
```
