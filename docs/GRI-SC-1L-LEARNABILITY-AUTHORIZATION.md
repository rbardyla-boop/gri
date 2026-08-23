# GRI-SC-1L — Branch-Free Learnability Authorization

**Status:** DEVELOPMENT SEARCH AUTHORIZED — SCIENTIFIC VERDICT FORBIDDEN

## 1. Question

The SC-1R construction and SC-1R.1 accounting audit established that the
branch-free residual form is representable and admissible inside the frozen
resource envelope. Its 80-epoch SGD smoke did not learn useful behavior.

GRI-SC-1L asks:

> Can the audited 57-operation branch-free primitive be learned reliably from
> the frozen training data, rather than only constructed by a deterministic
> representability solver?

This is a learnability investigation, not a scientific efficacy test and not
a new architecture.

## 2. Authorized scope

Only development searches over learning procedure are authorized:

- optimizer choice;
- learning rate and deterministic schedule;
- initialization within the declared parameterization;
- bounded iteration/epoch count;
- deterministic loss implementation used to fit the frozen training split.

Every run must be labelled `DEV_LEARNABILITY_ONLY` and must emit no scientific
verdict, advantage claim, or candidate promotion.

## 3. Immutable candidate

The candidate form is exactly the audited SC-1 Candidate B construction:

```text
semantic_code(WAIT)  = 0
semantic_code(event) = 1

u      = tanh(D ⊙ h + E[token])
h_next = h + semantic_code(token) · (u - h)
```

Immutable anchors:

```text
candidate source SHA-256:
64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218

candidate manifest SHA-256:
f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584

SC-1R representability receipt SHA-256:
efdce8201193e52931cbbc88c703c2a199ebcfc5cef0b178c13aa22251e831bc

SC-1R.1 accounting receipt SHA-256:
50e35bff74a0918342ee58b339bfc74e9dfb7f6462f59a302eff79335706135e
```

The candidate remains:

```text
state slots:       8
trainable params:  96
fixed params:      10
recurrent ops:    57
recurrent+query:  78
runtime selector comparisons: 0
```

## 4. Immutable scientific inputs

The following may not change during SC-1L:

- GRI-02B fixture bank, labels, fit/held-out split, and delay set;
- token alphabet and fixed semantic-code assignment;
- candidate source and resource manifest;
- GRI-02B operation rules and resource ceilings;
- state interface `token_id + persistent state`;
- serialization fields and persistent-state declaration;
- decoder/evaluation definitions used for development diagnostics;
- no task, fixture, label, delay, sequence-position, or query metadata access.

The frozen parent anchors remain:

```text
GRI-02B operation rules:
166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3

GRI-02B fixture bank:
f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960
```

## 5. Bounded development grid

The initial development grid is fixed before execution:

```text
seeds:                 20260820, 20260821, 20260822
training data:         fit split only
SGD learning rates:    0.003, 0.01, 0.03, 0.1
Adam learning rates:   0.0003, 0.001, 0.003
LBFGS:                 deterministic float64 constructive diagnostic only
epoch cap:             400 for SGD/Adam
LBFGS iteration cap:   100
post-result tuning:    forbidden within a recorded grid
```

Additional optimizer, schedule, initialization, or loss variants require a
new development authorization. No variant may alter the candidate formula or
resource accounting.

## 6. Required development record

Each run must record:

- candidate source and manifest hashes;
- optimizer, initialization, loss, seed, and iteration limits;
- fit and held-out smoke metrics;
- fixed-decoder diagnostic metrics where used;
- restart-smoke result;
- simulator preflight result;
- explicit `DEV_LEARNABILITY_ONLY` status;
- no scientific verdict field other than `FORBIDDEN`.

Development results may be summarized as:

```text
LEARNABILITY_SIGNAL
    a bounded learning procedure finds the declared construction reliably
    enough to justify a separate development decision.

NO_LEARNABILITY_SIGNAL
    the tested procedure/grid does not learn it.

INCONCLUSIVE
    the development harness or deterministic evidence is invalid.
```

None of these outcomes authorizes SC-2 or a scientific run. A learnability
signal only justifies a later decision about whether to freeze one candidate.

## 7. Forbidden changes

SC-1L may not:

- alter Candidate B’s formula, state, parameters, operations, or selector;
- add gates, memory vectors, clocks, counters, routing, geometry, or a second
  transition network;
- alter fixtures, splits, labels, decoder rules, precision rules, or budgets;
- use representability weights as a hidden scientific initialization without
  declaring that initialization in the development record;
- promote a smoke result to a scientific result;
- freeze a candidate for SC-2;
- start a human or external-data experiment.

## 8. Current boundary

```text
GRI-SC-0:   LOWER-BOUND DISPROVED BY CONSTRUCTION
GRI-SC-1:   DEV_SMOKE COMPLETE
GRI-SC-1R:  REPRESENTABLE
GRI-SC-1R.1: ACCOUNTING AUDIT PASS
GRI-SC-1L:  DEVELOPMENT SEARCH AUTHORIZED
GRI-SC-2:   NOT AUTHORIZED

SCIENTIFIC ADVANTAGE: NOT ESTABLISHED
MINIMALITY: NOT ESTABLISHED
SCIENTIFIC LEDGER: UNCHANGED
SUCCESSOR: NOT AUTHORIZED
```
