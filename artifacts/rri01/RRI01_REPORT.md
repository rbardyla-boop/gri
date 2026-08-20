# RRI-01 — Depth-Failure Archaeology

Terminal verdict: `RRI_01_RELATION_ERASURE`

## Per-seed diagnostic signatures

- Seed 1337: overthinking_state_erosion, update_stall, relation_erasure
- Seed 1338: overthinking_state_erosion, relation_erasure, readout_mismatch
- Seed 1339: overthinking_state_erosion, update_stall, relation_erasure
- Seed 1340: overthinking_state_erosion, update_stall, relation_erasure
- Seed 1341: overthinking_state_erosion, update_stall, relation_erasure

## Signature counts

- `overthinking_state_erosion`: 5/5
- `oversmoothing`: 0/5
- `update_stall`: 4/5
- `dynamical_instability`: 0/5
- `relation_erasure`: 5/5
- `readout_mismatch`: 1/5
- `gradient_influence_decay`: 0/5

## Aggregate intermediate-readout accuracy

| Step | Mean accuracy |
|---:|---:|
| 1 | .94722 |
| 4 | 1.00000 |
| 8 | .97500 |
| 16 | .81111 |
| 32 | .65556 |
| 64 | .60278 |
| 128 | .53333 |

The relation-separation score is the primary direct signature: it falls from
its early peak before or alongside the accuracy collapse in every seed. The
co-occurring signatures are state erosion/overthinking in 5/5 seeds and update
stall in 4/5. Oversmoothing, dynamical instability, and gradient/influence
decay do not meet their preregistered thresholds.

## Strong-versus-weak seed comparison

At step 64, seed 1337 has accuracy `.48611`, endpoint relation separation
`13.19`, off-diagonal cosine `.36535`, and node dispersion `.53426`. Seed 1341
has accuracy `.68056`, separation `3.75`, cosine `.03168`, and dispersion
`.83054`. The stronger seed is therefore not explained by less relation
separation loss; its state geometry remains more differentiated, while the
fixed diagnostic still detects relational-class erasure.

## Controls

- Trace equivalence: `True`
- Model immutable: `True`
- Training/optimizer updates: none

RRI-01 is diagnostic only. No repair or RRI-02 work is authorized by this report.
