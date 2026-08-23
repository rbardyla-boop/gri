# GRI-SC-3 — Scientific Run Authorization Contract

**Status:** `CONTRACT_FROZEN_BEFORE_EXECUTION`

This unit freezes one fail-closed scientific execution contract. It does not
start or authorize the scientific run.

```text
scientific execution: NOT AUTHORIZED
scientific verdict:   NOT RUN
SC-3 execution call:  NOT GRANTED
```

## Question

Does the frozen 57-operation branch-free Candidate B satisfy the unchanged
GRI-02B scientific gates, beat the unchanged GRI-01 parent and matched
stateless controls as preregistered, and receive causal credit from its
preserve/transform mechanism?

## Inherited freeze

SC-3 inherits the exact SC-2 candidate and training freeze. It does not select
another optimizer, alter Candidate B, or reinterpret the resource accounting.

```text
candidate:              GRI-SC-1-B-BRANCHFREE-RESIDUAL
source SHA-256:         64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218
candidate manifest:     f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584
state slots:            8
trainable parameters:   96
fixed code slots:       10
recurrent operations:   57
recurrent + query:      78
runtime selector ops:   0
optimizer:              SGD
learning rate:          0.1
epochs:                 400
seeds:                  20260820, 20260821, 20260822
```

The SC-2 freeze manifest, record, and verification receipt are required
parents. Their hashes, together with all GRI-02B and SC-1 anchors, are frozen
in the machine-readable contract.

## Scientific obligations

The single run must use:

- all 558 literal fixtures with the unchanged 350/208 fit/held-out split;
- held-out delays `64` and `128`, without fixture or split mutation;
- float64, float32, and recurrent q8 as required modes;
- float16 and bfloat16 as preregistered stress modes;
- the unchanged q8 rule: float32 transition arithmetic, state clipping,
  round-to-nearest-even at scale `1/127`, integer clipping, and quantization
  after every recurrent step;
- one fixed `scipy.optimize.linprog` decoder per task, fit only on fit states
  immediately before query, with wait-specific decoders forbidden;
- full serialization/restart at every token boundary, including the empty
  prefix and the boundary immediately before `QUERY`;
- the unchanged GRI-01 parent and matched stateless baseline as opponents;
- the finite-state control as a solvability oracle/reference, not an opponent;
- no-preserve, no-transform, and no-recurrence causal ablations;
- deterministic replay with source, configuration, environment, controls,
  ablations, and result hashes.

## Verdict function

```text
GRI_SC3_ADVANTAGE
    all candidate gates pass;
    the candidate remains within the frozen budget;
    parent/stateless opponents are beaten as preregistered;
    causal ablations fail as expected;
    restart and replay pass;
    no frozen artifact mismatches.

GRI_SC3_NO_ADVANTAGE
    a required candidate gate fails;
    a required opponent is scientifically equivalent;
    or causal ablations do not support mechanism credit.

GRI_SC3_INCONCLUSIVE
    harness, environment, serialization, replay, or artifact-integrity
    failure prevents inference.
```

Matching the finite-state oracle does not trigger `GRI_SC3_NO_ADVANTAGE`.

## Fail-closed rules

The runner must refuse execution and emit no scientific verdict on any missing
or mismatched source, manifest, parent anchor, fixture, split, budget, decoder,
control, ablation, environment, or replay hash. No manual repair, post-result
tuning, task removal, architecture change, new development search, or second
run is permitted.

## Anchors

```text
SC-3 contract SHA-256:
590d6606ff23cdfb02e9285f71772c9fab52d5b46fdd693a842ad83b5a242987

SC-2 freeze manifest SHA-256:
03ec6bc36c8b5d4d764bdbef3bccf875294c1b9b8512d23614643beef0638e9d

SC-2 verification receipt SHA-256:
469667f77a4adb4af0adaeb1d8f7dbeb49813712e2705e64230852c7bd4bbaa6

GRI-02B fixture bank SHA-256:
f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960

GRI-02B operation rules SHA-256:
166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3
```

## Boundary

```text
REPRESENTABLE: YES
IN-BUDGET: YES
BRANCH-FREE: YES
LEARNABILITY SIGNAL: YES
SC-2 FREEZE: VERIFIED
SC-3 CONTRACT: FROZEN
SCIENTIFIC RUN: NOT AUTHORIZED
SCIENTIFIC ADVANTAGE: NOT ESTABLISHED
MINIMALITY: NOT ESTABLISHED
```
