# DMC-05A — Conventional Memory Null + Cost Scaling

Terminal state: `DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES`

Conventional Pareto dominators: `recent_window_16`

## Capability

| System | Critical recall | Retrieval accuracy | Answer accuracy |
|---|---:|---:|---:|
| full_history_scan | 1.000000 | 1.000000 | 1.000000 |
| recent_window_16 | 1.000000 | 1.000000 | 1.000000 |
| frozen_fifo_16 | 0.000000 | 0.000000 | 0.025338 |
| random_16 | 0.244932 | 0.243243 | 0.287162 |
| exact_structured | 1.000000 | 1.000000 | 1.000000 |
| conventional_retrieval | 1.000000 | 1.000000 | 1.000000 |
| dmc04b | 1.000000 | 1.000000 | 1.000000 |
| dmc_retrieval_all_history | 1.000000 | 0.734797 | 0.765203 |

## Load 1024 resources

| System | Persistent records | Persistent bytes | Query inspected | Working records | Working bytes | Ingestion ns | Query ns | Online ns | Learned forwards |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full_history_scan | 1024.000 | 211854.443 | 1024.000 | 1024.000 | 211854.443 | 6823053.534 | 425801.739 | 7248855.273 | 0.000 |
| recent_window_16 | 16.000 | 1531.716 | 16.000 | 16.000 | 1531.716 | 3620884.898 | 60941.102 | 3681826.000 | 0.000 |
| frozen_fifo_16 | 16.000 | 1586.818 | 16.000 | 16.000 | 1586.818 | 196622.466 | 20745.864 | 217368.330 | 0.000 |
| random_16 | 16.000 | 1632.455 | 16.000 | 16.000 | 1632.455 | 6546343.523 | 21589.614 | 6567933.136 | 0.000 |
| exact_structured | 1024.000 | 250588.352 | 1.557 | 1.557 | 317.682 | 8900742.545 | 50142.273 | 8950884.818 | 0.000 |
| conventional_retrieval | 1024.000 | 250464.080 | 19.636 | 16.000 | 3215.750 | 8212810.170 | 93837.193 | 8306647.364 | 0.000 |
| dmc04b | 16.000 | 9514.261 | 16.000 | 16.000 | 3111.909 | 318070439.348 | 4479385.632 | 322549824.980 | 4.000 |
| dmc_retrieval_all_history | 1024.000 | 607261.898 | 1024.000 | 1024.000 | 124973.398 | 23460.202 | 129148695.720 | 129172155.923 | 65.000 |

## Gates

- `dmc_capability`: PASS — {"observed":1.0,"pass":true,"threshold":0.99}
- `exact_structured_capability`: PASS — {"observed":1.0,"pass":true,"threshold":0.99}
- `conventional_retrieval_capability`: PASS — {"observed":1.0,"pass":true,"threshold":0.99}
- `capability_match`: PASS — {"observed_max_gap":0.0,"pass":true,"threshold_max":0.01}
- `dmc_storage_ratio_1024`: PASS — {"observed":0.03796769194316558,"pass":true,"threshold_max":0.1}
- `conventional_bounded_working_set`: PASS — {"observed_max":16.0,"pass":true,"threshold_max":16}
- `matching_bounded_conventional_system`: PASS — {"observed":["recent_window_16","exact_structured","conventional_retrieval"],"pass":true,"threshold_min_count":1}
- `all_history_retention_ablation`: FAIL — {"observed_gap":0.23479729729729726,"pass":false,"threshold_max":0.01}

## Dominance checks

- `recent_window_16`: DOMINATES — {"bounded_working_records":true,"capability":true,"learned_forward_calls":true,"no_historical_training":true,"persistent_bytes":true,"persistent_records":true,"query_records_inspected":true,"retrieval_operations":true,"total_online_wall_time":true,"working_bytes":true}
- `frozen_fifo_16`: does not dominate — {"bounded_working_records":true,"capability":false,"learned_forward_calls":true,"no_historical_training":true,"persistent_bytes":true,"persistent_records":true,"query_records_inspected":true,"retrieval_operations":true,"total_online_wall_time":true,"working_bytes":true}
- `random_16`: does not dominate — {"bounded_working_records":true,"capability":false,"learned_forward_calls":true,"no_historical_training":true,"persistent_bytes":true,"persistent_records":true,"query_records_inspected":true,"retrieval_operations":true,"total_online_wall_time":true,"working_bytes":true}
- `exact_structured`: does not dominate — {"bounded_working_records":true,"capability":true,"learned_forward_calls":true,"no_historical_training":true,"persistent_bytes":false,"persistent_records":false,"query_records_inspected":true,"retrieval_operations":true,"total_online_wall_time":true,"working_bytes":true}
- `conventional_retrieval`: does not dominate — {"bounded_working_records":true,"capability":true,"learned_forward_calls":true,"no_historical_training":true,"persistent_bytes":false,"persistent_records":false,"query_records_inspected":false,"retrieval_operations":false,"total_online_wall_time":true,"working_bytes":false}

## Training accounting

Historical wall-time, energy, and dollar accounting: `TRAINING_COST_UNKNOWN`.
Reconstructable optimizer steps and example/case presentations are preserved in `training_accounting.json`; heterogeneous optimizer steps are not converted into a magic compute or dollar score.

## Boundary

This experiment uses a synthetic structured benchmark and no language tokenizer or expensive language model. The generator places all utility-eligible records at the end of each measured stream, so recent-window success is a benchmark-ordering result, not evidence that recency solves general memory. No real-language inference-cost advantage is established.
