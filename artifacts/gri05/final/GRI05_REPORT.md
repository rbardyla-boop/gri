# GRI-05 — Capacity-Matched SO(4) Verdict

## Execution identity

- Branch: `agent/gri-so4-capacity-match`
- Commit: `1fa9208d3b5b2d61eb35cf117d61d5e0a4622693`
- Frozen WORLD-0: unchanged
- WORLD-0 validator: `GRI_02_WORLD0_PASS`
- Resume audit: `GRI_RESUME_EQUIVALENCE_PASS`, audit seed 9090
- Parameter counts: baseline 30,912; SO(4) 30,912
- Runtime: CPU, Python 3.12.3, PyTorch 2.8.0+cu128, one Torch thread

## Per-seed results

| Model | Seed | Train | IID | D5 | D8 | D16 | D32 | D64 | Primary |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 1337 | 1.000 | 1.000 | 1.000 | 1.000 | .625 | .500 | .500 | .65625 |
| Baseline | 1338 | 1.000 | 1.000 | 1.000 | 1.000 | .875 | .750 | .625 | .81250 |
| Baseline | 1339 | 1.000 | 1.000 | 1.000 | 1.000 | .875 | .625 | .625 | .78125 |
| Baseline | 1340 | 1.000 | 1.000 | 1.000 | .875 | .750 | .750 | .625 | .75000 |
| Baseline | 1341 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | .750 | .750 | .87500 |
| SO(4) | 1337 | 1.000 | 1.000 | 1.000 | 1.000 | .500 | .250 | .125 | .46875 |
| SO(4) | 1338 | 1.000 | 1.000 | 1.000 | 1.000 | .375 | .250 | .375 | .50000 |
| SO(4) | 1339 | 1.000 | 1.000 | 1.000 | .625 | .250 | .250 | .250 | .34375 |
| SO(4) | 1340 | .3125 | .3125 | .250 | .125 | .125 | .125 | .125 | .12500 |
| SO(4) | 1341 | .21875 | .21875 | .125 | .250 | .250 | .125 | .125 | .18750 |

## Aggregates

| Model | Mean Train | Mean IID | Mean Primary | Primary SD |
|---|---:|---:|---:|---:|
| Baseline | 1.00000 | 1.00000 | .77500 | .08089 |
| SO(4) | .70625 | .70625 | .32500 | .16624 |

Primary difference, SO(4) − baseline: **−0.45000**.

## Preregistered gates

- Mean SO(4) train ≥ .95: **FAIL** (.70625).
- Mean SO(4) IID validation ≥ .95: **FAIL** (.70625).
- Primary mean improvement ≥ .05: **FAIL** (−.45).
- SO(4) primary SD ≤ 90% of baseline SD: **FAIL** (.16624 > .07280).

Implementation and execution are verified. The learning-advantage gate is not supported.

## Terminal verdict

`GRI_05_SO4_NO_ADVANTAGE`

Stop. No tuning or GRI-06 work is authorized by this experiment.
