# RRI-01R — Baseline Checkpoint Reconstruction

## Scope

This recovery unit reconstructed the five missing GRI-05 recurrent-baseline
final states. It did not reopen GRI-05, train SO(4), alter tracked model code,
or produce RRI-01 scientific evidence.

## Frozen identity

- Code commit: `1fa9208d3b5b2d61eb35cf117d61d5e0a4622693`
- Branch: `agent/gri-so4-capacity-match`
- WORLD-0: `GRI_02_WORLD0_PASS`, unchanged
- Tests: `36/36 PASS`
- Baseline: hidden 49, message 51, 30,912 trainable parameters
- Environment: Python 3.12.3, PyTorch 2.8.0+cu128, CPU, one Torch thread

## Recovery acceptance

All five per-seed metric rows reproduced exactly:

| Seed | Train | IID | D5 | D8 | D16 | D32 | D64 | Primary |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1337 | 1.000 | 1.000 | 1.000 | 1.000 | .625 | .500 | .500 | .65625 |
| 1338 | 1.000 | 1.000 | 1.000 | 1.000 | .875 | .750 | .625 | .81250 |
| 1339 | 1.000 | 1.000 | 1.000 | 1.000 | .875 | .625 | .625 | .78125 |
| 1340 | 1.000 | 1.000 | 1.000 | .875 | .750 | .750 | .625 | .75000 |
| 1341 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | .750 | .750 | .87500 |

The duplicate five-seed replay produced exact equality for every seed in:

- final model tensors;
- AdamW optimizer state;
- Python, NumPy, and PyTorch RNG state;
- final loss;
- model-state SHA-256;
- serialized checkpoint SHA-256.

The resulting checkpoints are admissible as frozen observational inputs for
RRI-01. RRI-01 itself has not started.

## Terminal verdict

`RRI_01R_CHECKPOINT_RECOVERY_PASS`
