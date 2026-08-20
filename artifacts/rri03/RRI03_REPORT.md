# RRI-03 — Extrapolation Stress Test

Evaluation-only on frozen RRI-02B checkpoints; no training performed.

## Primary and family results

| Model | Depth | Scale | Structure | Corruption | P_stress |
|---|---:|---:|---:|---:|---:|
| baseline | 0.55000 | 0.82500 | 0.64375 | 0.67500 | 0.67344 |
| anchor | 0.75000 | 0.97500 | 0.84375 | 0.85000 | 0.85469 |

## Paired P_stress

| Seed | Baseline | Anchor | Difference |
|---:|---:|---:|---:|
| 1337 | 0.53906 | 0.81250 | 0.27344 |
| 1338 | 0.70833 | 1.00000 | 0.29167 |
| 1339 | 0.62760 | 0.99219 | 0.36458 |
| 1340 | 0.69531 | 0.79688 | 0.10156 |
| 1341 | 0.79688 | 0.67188 | -0.12500 |

## Scenario means

| Scenario | Baseline | Anchor | Difference |
|---|---:|---:|---:|
| depth_128 | 0.55000 | 0.75000 | 0.20000 |
| depth_256 | 0.55000 | 0.75000 | 0.20000 |
| depth_512 | 0.55000 | 0.75000 | 0.20000 |
| scale_128 | 0.82500 | 0.97500 | 0.15000 |
| scale_256 | 0.82500 | 0.97500 | 0.15000 |
| scale_512 | 0.82500 | 0.97500 | 0.15000 |
| scale_1024 | 0.82500 | 0.97500 | 0.15000 |
| branching_paths | 0.55000 | 0.82500 | 0.27500 |
| distractor_paths | 0.67500 | 0.85000 | 0.17500 |
| simultaneous_chains | 0.67500 | 0.85000 | 0.17500 |
| new_compositions | 0.67500 | 0.85000 | 0.17500 |
| irrelevant_edges | 0.67500 | 0.85000 | 0.17500 |
| missing_irrelevant_facts | 0.67500 | 0.85000 | 0.17500 |
| contradictory_distractors | 0.67500 | 0.85000 | 0.17500 |

## Gates

- stress_primary_improvement_at_least_0.05: **PASS** (`0.18125`)
- depth_family_improvement_at_least_0.05: **PASS** (`0.19999999999999996`)
- paired_primary_wins_at_least_4: **PASS** (`4`)
- non_depth_families_not_more_than_0.05_below: **PASS** (`{'scale': 0.15000000000000002, 'structure': 0.19999999999999996, 'corruption': 0.17499999999999993}`)
- optimized_execution_equivalence: **PASS** (`True`)

Fast sparse execution equivalence: **PASS**

Seed 1341 remains included; its paired result is in `aggregate.json`.

## Terminal verdict

`RRI_03_STRESS_ADVANTAGE`
