# DMC-02 — 16-Slot Bounded Exact-Retention Evidence

Terminal state: `DMC_02_BOUNDED_EXACT_RETENTION_ADVANCES`

| Seed | Exact P_bounded | FIFO P_bounded | Random P_bounded | Exact−FIFO | Exact−Random |
|---:|---:|---:|---:|---:|---:|
| 1337 | 1.00000000 | 0.00000000 | 0.02361111 | 1.00000000 | 0.97638889 |
| 1338 | 1.00000000 | 0.00000000 | 0.01388889 | 1.00000000 | 0.98611111 |
| 1339 | 1.00000000 | 0.00000000 | 0.04166667 | 1.00000000 | 0.95833333 |
| 1340 | 1.00000000 | 0.00000000 | 0.02777778 | 1.00000000 | 0.97222222 |
| 1341 | 1.00000000 | 0.00000000 | 0.02361111 | 1.00000000 | 0.97638889 |

## Aggregate

- Exact mean/stdev: `1.00000000` / `0.00000000`
- FIFO mean/stdev: `0.00000000` / `0.00000000`
- Random mean/stdev: `0.02611111` / `0.01008261`

## Gates

- A_primary: **PASS** (observed `1.0`, threshold `0.95`)
- B_M1024: **PASS** (observed `1.0`, threshold `0.95`)
- C_SAL1024: **PASS** (observed `1.0`, threshold `0.95`)
- D_SUP_current_1024: **PASS** (observed `1.0`, threshold `0.95`)
- E_SUP_history_1024: **PASS** (observed `1.0`, threshold `0.95`)
- F_SHIFT: **PASS** (observed `1.0`, threshold `0.95`)
- G_FLOOD1024: **PASS** (observed `1.0`, threshold `0.95`)
- H_seed_consistency: **PASS** (observed `5`, threshold `5/5`)
- control fifo: **PASS** (observed `1.0`, threshold `0.4`)
- control random: **PASS** (observed `0.9738888888888889`, threshold `0.4`)
