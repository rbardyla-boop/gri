# GRI-01I — Precision / Robustness Bound

## Claim under test

For the exact frozen GRI-01H trajectories and post-hoc wait-specific
separators, task information remains usable only while both the state and the
decoder retain enough finite precision.

No cell, transition, readout, optimizer, or training run was changed. This
unit reads the stored H receipt and evaluates its existing separators.

## Check

Each H hidden state and its corresponding H separator was evaluated under:

- `float64`, `float32`, `float16`, and `bfloat16`, casting both state and
  separator coefficients;
- symmetric fixed-point hidden-state quantization at 16, 12, 8, 6, and 4
  bits over `[-1, 1]`, retaining the H separator in float64.

Usability requires finite scores, perfect accuracy, and a strictly positive
normalized geometric margin:

```text
minimum signed distance / ||w|| > 0
```

## Verdict

```text
PRECISION_FRAGILE
```

The final usable wait windows were:

| Task | float64 | float32 | float16 | bfloat16 | 16-bit | 12-bit | 8-bit | 6-bit | 4-bit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| correction | 24 | 19 | 9 | 6 | 17 | 12 | 9 | 6 | 6 |
| delayed bit | 25 | 19 | 9 | 8 | 16 | 12 | 9 | 7 | 7 |
| order | 28 | 22 | 12 | 11 | 19 | 15 | 11 | 10 | 10 |

The float64 endpoint normalized margins were approximately `1.16e-9`
(correction), `6.62e-10` (delayed bit), and `5.30e-10` (order). Thus the
late mathematical separators are already extremely precision-sensitive.

## Criteria

- Float64 reference reproduces the H wait windows: **PASS**.
- At least one finite representation loses usable waits for every task:
  **PASS**.
- Immediate loss under the configured modest-precision rule: **FAIL**;
  usable information survives beyond `WAIT 1` in all tasks.
- Precision-fragile classification: **PASS** for all three tasks.
- No architecture or training change: **PASS**.
- Deterministic replay: **PASS** after ignoring only `timestamp_utc`.
- Existing regression suite: **PASS**, 30 tests.

## Interpretation and credit assignment

GRI-01's late phase-local separability is not robust state. The information
window shortens materially under ordinary finite representations, with
float16/bfloat16 and 8-bit state quantization losing roughly half or more of
the float64 horizon. The effect is attributable to microscopic state
separation and large, phase-specific decoder sensitivity, not to a new cell
or optimizer choice.

The bounded requirement earned by the full diagnostic sequence is:

> A viable recurrent digital cell must preserve task-relevant distinctions
> with bounded state size, bounded precision, and a time-invariant semantic
> interpretation.

## Assumption register

- **Verified:** the H config and H receipt hashes match the frozen values in
  the I config.
- **Verified:** I reuses stored H trajectories and H separators; it performs
  no retraining.
- **Verified:** dtype and fixed-point rules are frozen in the I config before
  the final run.
- **Checkable but bounded:** the result is a finite-fixture robustness bound,
  not a general theorem about all recurrent representations.
- **Unfalsifiable here:** whether a future mechanism can satisfy the bounded
  precision requirement without excess state or complexity.

## Stop / continue

The GRI-01 diagnostic sequence is complete. Do not alter GRI-01 or promote a
new mechanism yet. Any future primitive must be a separately authorized
matched comparison with explicit preservation, precision, and ablation tests.

## Maturity status

GRI-01 is defined, specified, tested, falsified in its bounded claim,
replayed, and compared against controls. The result is mature as a bounded
negative diagnostic, not as a general impossibility claim.

## Evidence

```text
config SHA-256:         61adc50852289e5b1785fc448e6bea6eb53e23e5909df81558a9da9a81cc4f5f
implementation SHA-256: 123026faf7b83f978bbfaa638116e367857eb8f04b59b239d83426787ae13481
receipt SHA-256:        d4589bf562d8cf11561eb0387273f7a54f92928648ae65bf5203c7fd47de2295
replay:                 PASS
```
