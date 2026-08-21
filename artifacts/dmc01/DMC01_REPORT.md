# DMC-01 — Exact Episodic Memory Evidence

Terminal state: `DMC_01_EXACT_MEMORY_ADVANCES`

| Seed | Exact P_memory | No-memory P_memory | Shuffled P_memory | Exact−No-memory | Exact−Shuffled |
|---:|---:|---:|---:|---:|---:|
| 1337 | 1.00000000 | 0.12500000 | 0.00000000 | 0.87500000 | 1.00000000 |
| 1338 | 1.00000000 | 0.12500000 | 0.00000000 | 0.87500000 | 1.00000000 |
| 1339 | 1.00000000 | 0.12500000 | 0.00000000 | 0.87500000 | 1.00000000 |
| 1340 | 1.00000000 | 0.12500000 | 0.00000000 | 0.87500000 | 1.00000000 |
| 1341 | 1.00000000 | 0.12500000 | 0.00000000 | 0.87500000 | 1.00000000 |

## Gate results

- A_train: **PASS** (observed `1.0`, threshold `0.95`)
- B_iid: **PASS** (observed `1.0`, threshold `0.95`)
- C_P_memory: **PASS** (observed `1.0`, threshold `0.9`)
- D_exact_minus_nomemory: **PASS** (observed `0.875`, threshold `0.6`)
- E_R1024: **PASS** (observed `1.0`, threshold `0.9`)
- F_C1024: **PASS** (observed `1.0`, threshold `0.9`)
- G_S_current: **PASS** (observed `1.0`, threshold `0.95`)
- H_S_history: **PASS** (observed `1.0`, threshold `0.95`)
- I_D1024: **PASS** (observed `1.0`, threshold `0.9`)
- J_paired_consistency: **PASS** (observed `5`, threshold `5/5`)
- shuffled-content gate: **PASS** (observed `1.0`, threshold `0.4`)
