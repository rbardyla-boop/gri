# DMC-03 — Learned Selective Retention Evidence

Terminal state: `DMC_03_LEARNED_RETENTION_ADVANCES`

| Seed | Oracle P | Learned P | FIFO P | Random P | Shuffled-meta P |
|---:|---:|---:|---:|---:|---:|
| 1337 | 1.00000000 | 1.00000000 | 0.00000000 | 0.04444444 | 0.02083333 |
| 1338 | 1.00000000 | 1.00000000 | 0.00000000 | 0.01388889 | 0.02083333 |
| 1339 | 1.00000000 | 1.00000000 | 0.00000000 | 0.03472222 | 0.02083333 |
| 1340 | 1.00000000 | 1.00000000 | 0.00000000 | 0.02916667 | 0.02083333 |
| 1341 | 1.00000000 | 1.00000000 | 0.00000000 | 0.02916667 | 0.02083333 |

| Seed | w_mission | w_salience | bias |
|---:|---:|---:|---:|
| 1337 | 7.22988367 | 7.57814455 | -3.65022826 |
| 1338 | 8.09826088 | 7.74115038 | -3.94518209 |
| 1339 | 7.98667622 | 7.83159733 | -3.98020339 |
| 1340 | 7.68200302 | 7.42783308 | -3.82489038 |
| 1341 | 7.64377737 | 8.07898331 | -3.85884643 |

## Aggregate

- ORACLE_RETENTION_16 mean/stdev: `1.00000000` / `0.00000000`
- LEARNED_RETENTION_16 mean/stdev: `1.00000000` / `0.00000000`
- FIFO_16 mean/stdev: `0.00000000` / `0.00000000`
- RANDOM_16 mean/stdev: `0.03027778` / `0.01108504`
- SHUFFLED_METADATA_16 mean/stdev: `0.02083333` / `0.00000000`

## Differences

- oracle_minus_learned: `0.00000000`
- learned_minus_fifo: `1.00000000`
- learned_minus_random: `0.96972222`
- learned_minus_shuffled_metadata: `0.97916667`

## Gates

- A_primary: **PASS** (observed `1.0`, threshold `0.9`)
- B_oracle_gap: **PASS** (observed `0.0`, threshold `0.1`)
- C_M1024: **PASS** (observed `1.0`, threshold `0.9`)
- D_SAL1024: **PASS** (observed `1.0`, threshold `0.9`)
- E_SUP_current_1024: **PASS** (observed `1.0`, threshold `0.9`)
- F_SUP_history_1024: **PASS** (observed `1.0`, threshold `0.9`)
- G_SHIFT: **PASS** (observed `1.0`, threshold `0.9`)
- H_FLOOD1024: **PASS** (observed `1.0`, threshold `0.9`)
- I_seed_consistency: **PASS** (observed `5`, threshold `5/5`)
- J_FIFO_separation: **PASS** (observed `1.0`, threshold `0.6`)
- K_RANDOM_separation: **PASS** (observed `0.9697222222222223`, threshold `0.6`)
- metadata-use mechanism: **PASS** (observed `0.9791666666666666`, threshold `0.4`)
