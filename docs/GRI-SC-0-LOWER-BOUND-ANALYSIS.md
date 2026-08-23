# GRI-SC-0 — Selector-Cost Lower-Bound Analysis

## Result

```text
SELECTOR_COST_LOWER_BOUND_INCONCLUSIVE
```

This is a formal analysis only. It contains no candidate implementation, no
simulator search, no training, no scientific run, and no change to the
scientific ledger.

## Question tested

Under the frozen `token_id + persistent state` interface and the frozen
GRI-02B accounting model, must preserve/transform behavior consume one
additional comparison or dispatch operation beyond the 97-operation
recurrent ceiling?

## What follows from the semantics

Let `H` be the persistent state and let `F(x,h)` be the candidate transition
for token `x` and state `h`. The required behavior implies:

```text
F(WAIT, h) = h                         for task-relevant h
F(event, h) != h for some event, h     when transformation is required
```

Therefore the transition function must depend on the token’s semantic class.
That is a valid semantic lower bound:

```text
token-class dependence is necessary
```

It is not yet an operation lower bound:

```text
one explicit comparison/branch is necessary
```

The second statement does not follow from the first under the currently
permitted computation model.

## Why the operation lower bound is not proved

The frozen rules already permit token lookup and embedding values as part of
the recurrent step. Parameter loads inside a counted matrix-vector MAC are
also not counted separately. Consequently, token semantics may in principle
be encoded in the existing token-dependent arithmetic without an explicit
runtime equality test.

For example, a branch-free transition family could be described abstractly as

```text
e(WAIT) = 0
e(event) = event-specific value
F(h, e)  = h + G(h, e)
G(h, 0)  = 0
```

This is not an admissible 97-operation candidate as written: its arithmetic
cost and exact realizability remain to be established. It is sufficient to
show why an informal argument of the form “the cell must compare the token to
WAIT” is not a proof under an interface that already supplies token-dependent
values.

Likewise, under the narrower single-transform form

```text
F(x,h) = tanh(W h + E[x] + b)
```

an exact identity over an open continuous state domain is not generally
available from one affine map followed by `tanh`. But the frozen fixture
family has finitely many reachable states, and semantic equivalence could be
defined by exact state equality, readout equality, or task-level behavior.
Those alternatives produce different lower-bound questions. The prior
GRI-01E result was an empirical representability test, not a proof over every
branch-free parameterization or every admissible fixed embedding.

## Formal gap

A proof of an additional selector operation would need to freeze all of the
following:

- the exact candidate calculus, including whether token embeddings may encode
  transition classes;
- whether token-specific fixed parameters are counted as lookup, constant
  load, or already-paid arithmetic;
- the state domain over which `PRESERVE` means exact identity;
- whether readout-equivalent preservation is sufficient;
- whether branch-free nonlinear token-conditioned arithmetic is admissible;
- the exact parameter and operation cost of any such encoding.

GRI-SC-0 freezes the parent interface and ceilings, but those details are not
settled tightly enough to prove that every admissible implementation requires
one new comparison. Choosing restrictive answers after seeing the GRI-02C
failure would make the lower bound circular.

## Bounded conclusion

```text
PROVED:
  preserve/transform requires token-class-dependent transition behavior.

NOT PROVED:
  token-class dependence requires one additional comparison/dispatch
  operation beyond the existing 97-operation budget.

RESULT:
  SELECTOR_COST_LOWER_BOUND_INCONCLUSIVE
```

This result does not disprove the lower bound. It says the current formal
model does not settle it without further specification or a construction.

## Authorization consequence

The result permits a separate request for `GRI-SC-1` bounded `DEV_SMOKE`
search, but does not authorize it. Any such request would still need to freeze
one candidate, source and manifest hashes, exact accounting, and the
development-only status before simulator search begins.

No successor mechanism is authorized by this analysis.

## Canonical state

```text
GRI-01:    CLOSED — BOUNDED NEGATIVE
GRI-02A:   COMPLETE
GRI-02B:   COMPLETE
GRI-02C:   ALGORITHMIC FINDING SUPPORTED
GRI-02C.1: CLOSED — GRI02_NO_ADVANTAGE
GRI-SC-0:  LOWER-BOUND INCONCLUSIVE; SC-1 NOT AUTHORIZED

MINIMALITY: NOT ESTABLISHED
SUCCESSOR:  NOT AUTHORIZED
```
