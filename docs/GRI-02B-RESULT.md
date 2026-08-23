# GRI-02B — Executable Pre-Registration

## Status

```text
GRI02B_PREREGISTRATION_READY
CANDIDATE_PRESENT: false
CANDIDATE_VERDICT: NOT_RUN
IMPLEMENTATION: NOT AUTHORIZED
```

This unit freezes the evaluation environment only. It contains no candidate
cell, preserve mechanism, transform mechanism, training loop, optimizer run,
or architecture selection.

## Literal fixture bank

The machine-readable bank contains 558 literal fixtures:

| Family | Count |
|---|---:|
| preserve delayed bit | 18 |
| preserve correction | 36 |
| preserve order | 18 |
| transform correction | 324 |
| transform order | 162 |
| **total** | **558** |

There are 350 fit fixtures and 208 held-out fixtures. Decoder fitting uses only
delays `{0,1,2,4,8,16,32}`. Delays `64` and `128`, and every transform pair
containing one of them, remain held out. One fixed LP decoder is defined per
task across preserve and transform fixtures; wait-specific decoders are
forbidden.

## Frozen quantization

The q8 state mode uses float32 transition arithmetic and quantizes the
persistent state after every recurrent step, before serialization, and before
query readout:

```text
clip h to [-1,1]
q = clip(round_to_nearest_even(h / (1/127)), -127, 127)
h_q = q * (1/127)
```

Inputs and parameters are not quantized by this state-storage rule.

## Frozen operation counts

Using the recorded counting convention:

```text
GRI-01 d=8 parent: 170 parameters, 118 recurrent+query operations
matched GRU d=8:   506 parameters, 526 recurrent+query operations
q8 overhead:       57 operations, reported separately
```

The matched GRU uses one bias vector per gate and the explicitly recorded
three-gate equations. Counts are machine-checked by the preregistration
harness.

## Oracle and verdict checks

The explicit finite-state oracle passed all 558 fixtures and 32,154
serialize/restart cases. The preregistered verdict function self-test passed,
including the crucial rule that matching the finite-state oracle does not
block `GRI02_ADVANTAGE`, while parent equivalence does.

```text
GRI02B_REPLAY_PASS
30 regression tests passed
```

## Evidence hashes

```text
config SHA-256:          a8bf002449646151e32474b0b88d88f37e1cd9893bc4c9a90080c4495b1c693b
operation rules SHA-256: 166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3
fixture bank SHA-256:    f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960
harness SHA-256:          3d17031568614e6ec8043af10c7f71443f4ddfd8d35dea4bbcf578c12d38f217
receipt SHA-256:         b950588c82b1b6ca77a90d769362fdeb6ddb24750b7d0390a5c1f3ec861cc56f
contract SHA-256:        22d2a4a147d7e829f9cbcab246f6dba05bebffea6abdfa5b377aeef3171d660c
```

## Next gate

The next action is a separate implementation-authorization decision. No
candidate mechanism may be added merely because this preregistration is ready.
