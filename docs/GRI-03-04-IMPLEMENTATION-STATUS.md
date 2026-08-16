# GRI-03/04 — Implementation Status

This branch begins from the frozen WORLD-0 commit:

`1200050d1bbe99a7158e8482dacc534feb48d4c1`

## GRI-03 — Weight-Tied Graph Baseline

Implemented:

- structural WORLD-0 encoder;
- anonymous nodes (no entity-ID embedding);
- query-subject/query-object role features;
- asserted relation channels without inserting inverse answers;
- adjacency-only pair messaging;
- one weight-tied recurrent transition reused at arbitrary depth;
- deterministic training seed covering model initialization and sample order;
- machine-scored depth extrapolation.

The first smoke implementation exposed an all-to-all messaging defect and was repaired before commit. A second reproducibility defect (seed applied after model construction) was also repaired before commit.

### Baseline smoke results

All three 20-epoch seeds fit the small frozen training set and IID validation exactly. These are development smoke results, not a scientific verdict.

| Seed | Train | IID Val | D5 | D8 | D16 | D32 | D64 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1337 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.375 | 0.500 |
| 1338 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.875 | 0.750 |
| 1339 | 1.000 | 1.000 | 1.000 | 0.875 | 0.375 | 0.375 | 0.375 |

The same seed-1337 run was replayed and its JSON report was byte-identical.

Interpretation allowed at this stage: the benchmark exposes a clear out-of-distribution depth challenge even after perfect short-depth fitting, and seed variance at long depths is material.

Interpretation not allowed: GRI advantage, Transformer inferiority, or general reasoning superiority.

## GRI-04 — SO(4) Geometric Core

Implemented:

- local SO(4) frames;
- exact base connection `U_ij = Q_i Q_j^T`;
- transport from sender frame into receiver frame;
- invariant Gram features;
- equivariant geometric messages formed from invariant coefficients;
- invariant scored readout;
- weight-tied recurrence.

Verified by unit tests:

- exact canonical-state transport under independent frames;
- output invariance across independently randomized local SO(4) frames within floating-point tolerance.

The geometric model has **not** passed a matched learning/advantage gate. A short smoke run was insufficient and is not treated as evidence for or against the geometry hypothesis.

## Current gate

`GRI_GEOMETRY_IMPLEMENTATION_VALID` is supported only at the structural/invariance-test level.

`GRI_GEOMETRY_ADVANTAGE` is **NOT TESTED**.

Dimensional memory, learned connections, curvature/holonomy features, and E8 remain unauthorized as mainline additions until the geometric baseline receives a matched training/evaluation pass.
