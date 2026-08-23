# LCB Failure Map v0 — Replication Note

Date: 2026-08-23

## Purpose

The first same-landscape nonequilibrium sweep contained a small apparent retention increase at `epsilon=0.25` in one seed. This note tests whether that was a stable effect before attributing mechanism credit.

## Repeated-seed test

Model:

```text
U(x,y) = (x^2-1)^2/4 + y^2/2
dX = [-grad U + epsilon J grad U]dt + sqrt(2D)dW
D = 0.10
T = 60
```

Eight independent seeds were run for each `epsilon`, 400 trajectories per seed.

| epsilon | mean end-correct | SD | mean no-flip survival | SD | mean estimated EPR |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.5744 | 0.0209 | 0.1566 | 0.0128 | 0.000 |
| 0.25 | 0.5631 | 0.0238 | 0.1428 | 0.0134 | 0.166 |
| 0.50 | 0.5434 | 0.0222 | 0.1450 | 0.0170 | 0.664 |
| 1.00 | 0.5356 | 0.0095 | 0.0981 | 0.0160 | 2.673 |
| 2.00 | 0.5031 | 0.0313 | 0.0313 | 0.0069 | 10.983 |
| 4.00 | 0.5019 | 0.0124 | 0.0006 | 0.0012 | 48.954 |

The one-seed `epsilon=0.25` improvement did not reproduce. The repeated-seed mean is below equilibrium on both end-correct and no-flip survival.

## Time-step convergence attack

To test whether the degradation was a coarse Euler-Maruyama artifact, the comparison was repeated at `dt = 0.02`, `0.01`, and `0.005` for `epsilon = 0, 1, 2`, with four seeds and 500 trajectories per condition over `T = 40`.

No-flip survival:

| dt | eps=0 | eps=1 | eps=2 |
|---:|---:|---:|---:|
| 0.020 | 0.3055 | 0.2185 | 0.0745 |
| 0.010 | 0.2780 | 0.2065 | 0.1065 |
| 0.005 | 0.2905 | 0.2050 | 0.1200 |

The exact numerical values move with discretization and Monte Carlo noise, but the ordering survives refinement: stronger irreversible circulation produces substantially worse finite-horizon retention than the equilibrium control under the same stationary landscape.

## Updated interpretation

```text
ONE-SEED SMALL-EPS IMPROVEMENT:   NOT REPRODUCED
STRONG-CIRCULATION DEGRADATION:   REPRODUCED ACROSS SEEDS
TIMESTEP-ARTIFACT EXPLANATION:    NOT SUPPORTED BY dt REFINEMENT
```

This still does **not** prove that all nonequilibrium currents harm memory. It proves only that positive entropy production / circulating probability current is not sufficient for improved memory, even when the stationary distribution is held fixed exactly.

The successor mechanism must therefore be more specific than `dissipation` or `nonequilibrium`.