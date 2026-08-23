# GRI-SC-2 — Candidate Freeze

**Status:** `FROZEN_BEFORE_SCIENTIFIC_RUN`

## Authorization

SC-2 freezes one exact Candidate B configuration for a possible later
scientific run. It does not authorize that run.

```text
scientific execution: FORBIDDEN
scientific verdict:    FORBIDDEN
SC-3:                  NOT AUTHORIZED
```

The selected configuration is SGD because both SGD `0.1` and Adam `0.003`
met the SC-1L three-seed development criterion; SGD is the simpler procedure
and preserves continuity with the parent training protocol. This selection was
made before any scientific execution.

## Frozen candidate

```text
candidate:              GRI-SC-1-B-BRANCHFREE-RESIDUAL
source SHA-256:         64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218
manifest SHA-256:       f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584
persistent state slots: 8
trainable parameters:   96
fixed code slots:       10
recurrent operations:   57
recurrent + query:      78
runtime selector ops:   0
```

The candidate formula remains:

```text
semantic_code(WAIT) = 0
semantic_code(event) = 1
u = tanh(D ⊙ h + E[token])
h_next = h + semantic_code(token) · (u - h)
```

No source or candidate manifest was modified.

## Frozen training

```text
optimizer:       SGD
learning rate:   0.1
epochs:           400
momentum:         0
weight decay:     0
seeds:            20260820, 20260821, 20260822
training data:    fit split only
initialization:   default seeded Candidate B initialization
witness weights:  forbidden
post-result tune: forbidden
```

## Frozen evaluation

The scientific run, if separately authorized as SC-3, must use the unchanged
GRI-02B fixture bank, split, decoder protocol, q8 rule, serialization format,
operation accounting, and verdict function.

Required evaluation includes:

- float64, float32, and recurrent q8; float16 and bfloat16 as preregistered
  stress modes;
- one fixed decoder per task, fit only on fit states before the query;
- all 558 fixtures and all registered held-out delays;
- full serialization/restart checks at every token boundary;
- unchanged GRI-01 parent, finite-state oracle, stateless baseline, and the
  no-preserve, no-transform, and no-recurrence ablations;
- deterministic replay with implementation, configuration, environment, and
  result hashes.

## Anchors

```text
freeze manifest SHA-256:
03ec6bc36c8b5d4d764bdbef3bccf875294c1b9b8512d23614643beef0638e9d

SC-1R.1 accounting receipt:
50e35bff74a0918342ee58b339bfc74e9dfb7f6462f59a302eff79335706135e

SC-1L authorization:
25142cc2d044d3d07c1459ea9e345d6c2f87141876c6ac8588c8149d420712d4

SC-1L result:
b91a3fd10e3df7a1f24f301bd199a1d27b3938720f0fc8a635de51fb476df0af

GRI-02B fixture bank:
f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960

GRI-02B operation rules:
166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3
```

## Boundary

```text
REPRESENTABLE: YES
IN-BUDGET: YES
BRANCH-FREE: YES
LEARNABILITY SIGNAL: YES
SC-2 FREEZE: COMPLETE
SCIENTIFIC RUN: NOT AUTHORIZED
SCIENTIFIC ADVANTAGE: NOT ESTABLISHED
MINIMALITY: NOT ESTABLISHED
```
