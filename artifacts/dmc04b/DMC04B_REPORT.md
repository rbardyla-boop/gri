# DMC-04B — Frozen Learned Memory Integration Evidence

Terminal state: `DMC_04B_COMBINED_LEARNED_MEMORY_ADVANCES`

## Primary retrieval

| Pair seed | Oracle+Oracle P_R | Learned+Learned P_R | OracleRet+LearnedRet P_R | LearnedRet+OracleRet P_R |
|---:|---:|---:|---:|---:|
| 1337 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 1338 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 1339 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 1340 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 1341 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |

## Primary answer

| Pair seed | Learned+Learned P_answer |
|---:|---:|
| 1337 | 1.000000 |
| 1338 | 1.000000 |
| 1339 | 1.000000 |
| 1340 | 1.000000 |
| 1341 | 1.000000 |

## Aggregate modes

| Mode | P_R mean | P_R std | P_answer mean | P_answer std |
|---|---:|---:|---:|---:|
| oracle_oracle | 1.000000 | 0.000000 | 1.000000 | 0.000000 |
| oracle_retention_learned_retrieval | 1.000000 | 0.000000 | 1.000000 | 0.000000 |
| learned_retention_oracle_retrieval | 1.000000 | 0.000000 | 1.000000 | 0.000000 |
| learned_learned | 1.000000 | 0.000000 | 1.000000 | 0.000000 |
| fifo_learned | 0.000000 | 0.000000 | 0.174500 | 0.024566 |
| random_retention_learned | 0.000000 | 0.000000 | 0.143500 | 0.017073 |
| learned_random_retrieval | 0.072500 | 0.000000 | 0.157500 | 0.000000 |

## Boundary

This is evaluation only. The frozen DMC-03 retention scorers, frozen DMC-04R2 retrievers, and native seed-1337 decoder were loaded read-only. No joint training, optimizer, backward pass, adapter, feature change, or DMC-05 step was executed.
