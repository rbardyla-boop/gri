# GRI-SC-1R — Branch-Free Representability Analysis

## Result

```text
REPRESENTABLE
```

This is a constructive analysis of the declared SC-1 Candidate B formula. It
is not a scientific run, does not freeze a candidate, and cannot issue a
scientific verdict.

## Declared form

```text
u      = tanh(D ⊙ h + E[token])
r      = u - h
h_next = h + E[token][semantic_code] · r

semantic_code(WAIT) = 0
semantic_code(other) = 1
```

The semantic code is a fixed first coordinate of the existing token embedding.
The transition path performs no equality comparison or branch. It uses:

```text
state slots:       8
trainable params:  96
fixed params:      10
recurrent ops:    57
recurrent+query:  78
```

## Constructive solver

The deterministic float64 LBFGS solver used starts `0`, `1`, and `2`. It
optimized only the declared diagonal transform, token embedding content
coordinates, and one linear decoder per task using fit states. It then fit
independent LP decoders on fit states only and evaluated those fixed decoders
on held-out states.

All three starts produced:

```text
fit accuracy:       1.0
held-out accuracy:  1.0
all-fixture accuracy: 1.0
```

The minimum LP geometric margins by task and solver start were:

```text
start 0: correction 0.8093, delayed_bit 0.2895, order 0.9053
start 1: correction 0.9181, delayed_bit 0.8335, order 0.9342
start 2: correction 0.9323, delayed_bit 0.8975, order 0.9361
```

This establishes that the branch-free residual form can represent the frozen
fixture behavior under the declared state, parameter, and operation envelope.

## Interpretation boundary

The earlier 80-epoch SGD smoke failure was therefore a learning/search failure
for this formulation, not evidence that the formulation is unrepresentable.
This result does not establish:

- a scientific advantage;
- learnability under the frozen GRI-02C training protocol;
- generalization outside the frozen fixture family;
- minimality or a lower bound;
- authorization for SC-2 or a scientific run.

The next possible work would require a separate development authorization for
an improved constructive/learning procedure. No such authorization is issued
here.

GRI-SC-1R.1 subsequently audited the source line-by-line and passed the
accounting closure. Candidate B is therefore an admissible in-budget
counterexample to the claim that an additional explicit selector operation is
necessary. This changes the formal SC-0 subproblem result, not the scientific
ledger.

## Evidence hashes

```text
SC-0 contract SHA-256:
5174be19336f0f30597a22f78917b189708fe406f4f588dccc2989bd4b642e50

Candidate B source SHA-256:
64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218

Candidate B manifest SHA-256:
f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584

Solver SHA-256:
e4a45deff90cf1f75cbb81c86fc671a781f52b150edb11ffe2158bdebfeb2920

Receipt SHA-256:
efdce8201193e52931cbbc88c703c2a199ebcfc5cef0b178c13aa22251e831bc
```

## Current boundary

```text
GRI-SC-0:  LOWER-BOUND DISPROVED BY SC-1R.1 CONSTRUCTION
GRI-SC-1:  DEV_SMOKE COMPLETE
GRI-SC-1R: REPRESENTABLE — ANALYSIS ONLY
GRI-SC-1R.1: ACCOUNTING AUDIT PASS — SC-0 LOWER BOUND DISPROVED
GRI-SC-2:  NOT AUTHORIZED
SCIENTIFIC LEDGER: UNCHANGED
SUCCESSOR: NOT AUTHORIZED
```
