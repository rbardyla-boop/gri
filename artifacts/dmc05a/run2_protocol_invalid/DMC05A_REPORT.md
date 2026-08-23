# DMC-05A — Conventional Memory Null + Cost Scaling

Terminal state: `DMC_05A_BOUNDED_MEMORY_ADVANTAGE`

## Capability

| System | Critical recall | Retrieval accuracy | Answer accuracy |
|---|---:|---:|---:|
| full_history_scan | 1.000000 | 0.734797 | 0.765203 |
| recent_window_16 | 1.000000 | 1.000000 | 1.000000 |
| frozen_fifo_16 | 0.000000 | 0.000000 | 0.025338 |
| random_16 | 0.244932 | 0.243243 | 0.287162 |
| exact_structured | 1.000000 | 0.734797 | 0.765203 |
| conventional_retrieval | 0.932432 | 0.734797 | 0.765203 |
| dmc04b | 1.000000 | 1.000000 | 1.000000 |
| dmc_retrieval_all_history | 1.000000 | 0.734797 | 0.765203 |

## Load 1024 resources

| System | Persistent records | Persistent bytes | Query inspected | Working records | Query ns | Learned forwards |
|---|---:|---:|---:|---:|---:|---:|
| full_history_scan | 1024.000 | 607261.898 | 1024.000 | 1024.000 | 6171838.114 | 0.000 |
| recent_window_16 | 16.000 | 9514.261 | 16.000 | 16.000 | 120329.875 | 0.000 |
| frozen_fifo_16 | 16.000 | 9369.182 | 16.000 | 16.000 | 80713.602 | 0.000 |
| random_16 | 16.000 | 9490.170 | 16.000 | 16.000 | 136342.455 | 0.000 |
| exact_structured | 1024.000 | 104681.716 | 32.580 | 1.000 | 637087.898 | 0.000 |
| conventional_retrieval | 1024.000 | 104425.716 | 1024.000 | 16.000 | 2504765.682 | 0.000 |
| dmc04b | 16.000 | 9514.261 | 16.000 | 16.000 | 4128636.877 | 4.000 |
| dmc_retrieval_all_history | 1024.000 | 607261.898 | 1024.000 | 1024.000 | 91788191.957 | 65.000 |

## Gates

- `dmc_capability`: PASS — {"observed":1.0,"pass":true,"threshold":0.99}
- `exact_structured_capability`: FAIL — {"observed":0.7652027027027027,"pass":false,"threshold":0.99}
- `conventional_retrieval_capability`: FAIL — {"observed":0.7652027027027027,"pass":false,"threshold":0.99}
- `capability_match`: FAIL — {"observed_max_gap":0.23479729729729726,"pass":false,"threshold_max":0.01}
- `dmc_storage_ratio_1024`: PASS — {"observed":0.09088751823574295,"pass":true,"threshold_max":0.1}
- `conventional_bounded_working_set`: PASS — {"observed_max":16.0,"pass":true,"threshold_max":16}
- `all_history_retention_ablation`: FAIL — {"observed_gap":0.23479729729729726,"pass":false,"threshold_max":0.01}

## Training accounting

Historical wall-time, energy, and dollar accounting: `TRAINING_COST_UNKNOWN`.
Reconstructable optimizer steps and example/case presentations are preserved in `training_accounting.json`; heterogeneous optimizer steps are not converted into a magic compute or dollar score.

## Boundary

This experiment uses a synthetic structured benchmark and no language tokenizer or expensive language model. It can establish a bounded storage/query tradeoff, not a real-language inference-cost advantage.
