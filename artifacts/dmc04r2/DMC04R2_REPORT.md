# DMC-04R2 — Fixed-Decoder Learned Associative Retrieval Evidence

Terminal state: `DMC_04R2_LEARNED_RETRIEVAL_ADVANCES`

## Primary retrieval metrics

| Seed | Oracle P_R | Learned P_R | Random P_R | Exact-token P_R | A-only P_R | B-only P_R | Shuffled-query P_R |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1337 | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |
| 1338 | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |
| 1339 | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |
| 1340 | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |
| 1341 | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |

| Aggregate | Oracle P_R | Learned P_R | Random P_R | Exact-token P_R | A-only P_R | B-only P_R | Shuffled-query P_R |
|---|---:|---:|---:|---:|---:|---:|---:|
| mean | 1.000000 | 1.000000 | 0.062500 | 0.062500 | 0.375000 | 0.500000 | 0.000000 |

## Learned final-answer metrics

| Seed | Learned P_answer |
|---:|---:|
| 1337 | 1.000000 |
| 1338 | 1.000000 |
| 1339 | 1.000000 |
| 1340 | 1.000000 |
| 1341 | 1.000000 |
| mean | 1.000000 |

## Gates

- `A_P_retrieval`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `B_P_answer`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `C_oracle_gap`: PASS — {"observed": 0.0, "pass": true, "threshold_max": 0.1}
- `D_composition`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `E_hard_negatives`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `F_current`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `G_history`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `H_noise32`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.9}
- `I_seed_consistency`: PASS — {"count": 5, "pass": true, "required_count": 5, "threshold": 0.85}
- `J_random_separation`: PASS — {"observed": 0.9375, "pass": true, "threshold": 0.6}
- `K_exact_token_separation`: PASS — {"observed": 0.9375, "pass": true, "threshold": 0.6}
- `two_attribute_A_only`: PASS — {"observed": 0.625, "pass": true, "threshold": 0.3}
- `two_attribute_B_only`: PASS — {"observed": 0.5, "pass": true, "threshold": 0.3}
- `query_cue_mechanism`: PASS — {"observed": 1.0, "pass": true, "threshold": 0.4}

## Boundary

This evidence unit uses only the frozen DMC-04A memory, one native frozen seed-1337 decoder, and the 128-parameter DMC-04P matcher. It does not establish cross-seed latent interoperability, learned retention, semantic memory, consolidation, or DMC-03 integration.
