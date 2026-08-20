# RRI-02C — Immutable Anchor Mechanism Replication

Analysis commit: `81efb597deffab4f67d033161b4046417b5cbf9e`

## Baseline replication

Replication gate: **PASS**

| Step | Baseline accuracy | Anchor accuracy |
|---:|---:|---:|
| 1 | 0.94722222 | 0.94722222 |
| 4 | 1.00000000 | 1.00000000 |
| 8 | 0.97500000 | 1.00000000 |
| 16 | 0.81111111 | 0.96666667 |
| 32 | 0.65555556 | 0.84166667 |
| 64 | 0.60277778 | 0.80000000 |
| 128 | 0.53333333 | 0.73055556 |

## CTI mechanism gate

| Seed | Baseline CTI | Anchor CTI | Anchor − baseline |
|---:|---:|---:|---:|
| 1337 | 0.50000000 | 0.37500000 | -0.12500000 |
| 1338 | 0.62500000 | 0.00000000 | -0.62500000 |
| 1339 | 0.75000000 | 0.00000000 | -0.75000000 |
| 1340 | 0.37500000 | 0.25000000 | -0.12500000 |
| 1341 | 0.25000000 | 0.75000000 | 0.50000000 |

Mean baseline CTI: `0.50000000`
Mean anchor CTI: `0.27500000`
Mean reduction: `0.45000000`
M1: **PASS**
M2: **PASS** (4/5)

## Signature counts

| Signature | Baseline | Anchor |
|---|---:|---:|
| overthinking_state_erosion | 5/5 | 3/5 |
| oversmoothing | 0/5 | 0/5 |
| update_stall | 4/5 | 2/5 |
| dynamical_instability | 0/5 | 0/5 |
| relation_erasure | 5/5 | 3/5 |
| readout_mismatch | 1/5 | 1/5 |
| gradient_influence_decay | 0/5 | 0/5 |

## Seed 1341

Seed 1341 was retained. Its paired CTI and persistence values are recorded in `paired_cti.json`; no post-hoc exclusion or tuning was performed.

## Terminal verdict

`RRI_02C_ANCHOR_MECHANISM_SUPPORTED`

No training, optimizer step, or RRI-02D work was performed.
