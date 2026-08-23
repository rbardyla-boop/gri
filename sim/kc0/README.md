# KC-0 — Knowledge Cell development bank

This directory is a separate development fixture bank for the Small-Info
project. It does not modify or extend the frozen GRI-SIM-0 candidate protocol
and it does not authorize a knowledge-cell candidate or a scientific run.

The bank freezes literal knowledge packets, query fixtures, fit/held-out
sequence references, and trial cards for KC-0A through KC-0J:

```text
EAT → REMEMBER → PRESSURE → DIVIDE → SPECIALIZE
     → SHARE → LINEAGE → ECOLOGY → ADVERSARIAL FOOD → COUNTERFACTUAL
```

The trial cards deliberately defer thresholds, candidate interfaces, resource
accounting, and verdict functions until each stage receives its own
authorization. This prevents a fixture bank from being mistaken for evidence.

Validate the bank with:

```bash
python3 sim/kc0/validate_bank.py
```

Expected status:

```text
PASS — DEV_TRIAL_BANK_ONLY
```

There is no candidate implementation, optimizer, population engine, or
scientific result in this directory.

## KC-1A lifecycle gate

The first isolated cell is deliberately non-learning and non-reproductive:
eight integer value slots plus eight occupancy bits, with no global counter.
Run its lifecycle qualification with:

```bash
python3 sim/kc0/kc1a/lifecycle.py \
  --receipt artifacts/results/kc1a_lifecycle_receipt.json
```

The gate checks cold start, deterministic stepping, canonical serialization,
restart at every active-token boundary, static containment/accounting, and
mounting all KC-0 sequences. Its only allowed result is
`KC_1A_LIFECYCLE_PASS` or `KC_1A_LIFECYCLE_FAIL`; it cannot issue a scientific
verdict.

## KC-1B-D retention characterization

KC-1B-D uses the frozen KC-1A source without modification. It records matched
correct-packet, no-packet, and wrong-packet traces at delays `0, 1, 2, 4, 8,
16`, with standard and altered distractors. It also records raw state/readout
values, full/value-only/occupancy-only probes, and restart-at-delay equality.

```bash
python3 sim/kc0/kc1b/characterize.py \
  --receipt artifacts/results/kc1b_dev_characterization_receipt.json
```

This is development characterization only. Its terminal outputs are
`KC_1B_DEV_COMPLETE` or `KC_1B_DEV_INVALID`; no retention threshold or
scientific verdict is defined.

## KC-1C-D interference topology

KC-1C-D keeps KC-1A unchanged and varies only collision presence, count, and
position at a fixed 16-distractor sequence length. It also runs target
re-observation recovery and the complete 8-by-21 stored-slot/incoming-packet
matrix.

```bash
python3 sim/kc0/kc1c/characterize.py \
  --receipt artifacts/results/kc1c_dev_interference_receipt.json
```

Its only outputs are `KC_1C_DEV_COMPLETE` or `KC_1C_DEV_INVALID`; no
interference threshold or scientific verdict is defined.

## KC-1D-D capacity and saturation

KC-1D-D characterizes loads from 1 through 16 observed packets, under- and
over-capacity order variants, recency sequences, and whole-bank restart.
Current versus historical packet recoverability is recorded separately from
occupied-slot count.

```bash
python3 sim/kc0/kc1d/characterize.py \
  --receipt artifacts/results/kc1d_dev_capacity_receipt.json
```

Its only outputs are `KC_1D_DEV_COMPLETE` or `KC_1D_DEV_INVALID`; no capacity
threshold or scientific verdict is defined.
