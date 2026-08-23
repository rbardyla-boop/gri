# GRI-SC-0 — Selector-Cost Authorization Contract

**Status:** SPECIFICATION-ONLY AUTHORIZATION — NO CANDIDATE AUTHORIZED

## 1. Research question

GRI-SC-0 remains inside the original Small-Info Primitive question. Selector
cost is a subproblem of primitive minimization, not a new project identity:

```text
minimum persistent state
+ minimum transition machinery
+ minimum semantic-control cost
needed for reliable recurrent computation
```

The closed GRI-02C.1 audit found that the identity-preserve candidate solves
the frozen preserve/transform fixtures but exceeds the frozen GRI-01 resource
envelope because its executable selector adds one comparison.

GRI-SC-0 asks:

> Is an explicit semantic-selection operation necessary to obtain
> preserve/transform behavior under the frozen GRI budget, or can equivalent
> behavior be realized within the existing 97-operation recurrent ceiling?

The primary first route is a lower-bound analysis:

> Under the frozen interface and accounting model, does distinguishing
> `WAIT` from information-changing tokens require at least one additional
> discrimination operation?

No result is assumed. A proof attempt may conclude `PROVED`, `DISPROVED`, or
`INCONCLUSIVE`.

## 2. Scientific boundary

This contract does not authorize a new architecture, successor mechanism, or
scientific run. It authorizes only:

1. a formal lower-bound analysis; and
2. if that analysis is inconclusive, a bounded development-only search for
   implementations inside the existing resource envelope.

The current GRI-02C raw algorithmic finding and GRI-02C.1 formal verdict are
immutable inputs:

```text
GRI-02C:   ALGORITHMIC FINDING SUPPORTED
GRI-02C.1: FORMAL GRI02_NO_ADVANTAGE
```

## 3. Frozen parent references

The following references are read-only and may not be replaced, regenerated,
or weakened:

```text
parent GRI-02B config SHA-256:
a8bf002449646151e32474b0b88d88f37e1cd9893bc4c9a90080c4495b1c693b

operation rules SHA-256:
166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3

fixture bank SHA-256:
f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960

GRI-02B harness SHA-256:
3d17031568614e6ec8043af10c7f71443f4ddfd8d35dea4bbcf578c12d38f217

GRI-SIM-0 bundle SHA-256:
8ffd166a7f9a9f0f5a894230c1c38a14d74c0364331ba1314f2c2d81a3dc0493
```

Frozen resource envelope:

```text
persistent state slots:             8
trainable parameters:             170
recurrent operations maximum:      97
recurrent + query maximum:        118
```

## 4. Frozen interface for the lower-bound question

The candidate receives only:

```text
token_id + persistent state
```

The candidate does not receive fixture ids, labels, task names, delay counts,
sequence positions, query horizons, or future tokens. The simulator owns the
recurrence loop and calls the candidate transition once per active token.

The analysis must distinguish two semantic requirements:

```text
PRESERVE:  WAIT must leave task-relevant state unchanged
TRANSFORM: information-changing tokens must update task-relevant state
```

The lower-bound target is specifically the cost of discriminating those
transition semantics under the frozen interface and operation model. It must
not silently substitute a different interface or a different definition of
semantic equivalence.

## 5. Frozen accounting model

Use the GRI-02B operation rules without modification. In particular:

```text
comparison / branch predicate: one operation
token lookup:                   one operation
state copy:                     one operation per scalar copy
nonlinearity:                   one operation per scalar activation
```

The existing parent reference is:

```text
97 recurrent operations
118 recurrent-plus-query operations
```

Any comparison or dispatch performed inside candidate code is candidate cost.
An external transition class is admissible only if it is an actual input to
the candidate before its transition executes and is explicitly declared in
the candidate interface. A manifest assertion alone is insufficient.

## 6. Lower-bound analysis requirements

The first deliverable is a proof-oriented artifact, not candidate code. It
must state:

- the exact computational model and allowed primitives;
- whether token identity is available as an indexed input or only as a vector;
- what counts as semantic equivalence to the preserve/transform behavior;
- whether fixed token-specific parameters count as a lookup, constant load, or
  no additional operation under the frozen rules;
- whether a branch-free arithmetic encoding is allowed;
- whether a candidate may use the existing embedding lookup, bias, matrix
  multiply, nonlinearity, or readout to encode the distinction;
- the assumptions under which a lower bound is claimed;
- a counterexample if the bound is disproved;
- the precise reason for `INCONCLUSIVE` if the model leaves a route open.

The analysis may not claim a universal lower bound from an informal statement
that “the model must know whether the token is WAIT.” It must show why every
admissible implementation either performs an equivalent discrimination or
cannot satisfy the frozen semantic behavior.

## 7. Bounded development search, only if needed

If the lower-bound analysis is inconclusive, GRI-SC-1 may be separately
authorized for `DEV_SMOKE` search only. Its admissible space is limited to:

- reusing arithmetic already counted in the 97 operations;
- folding preservation into the transform rule;
- encoding semantics in token embeddings or fixed parameters;
- removing or repurposing an existing operation so selector cost is absorbed;
- implementations with no wider state, extra gates, extra memory, clock,
  phase variable, routing, geometry, or learned graph.

Every search candidate must use GRI-SIM-0’s narrow `token_id + state` protocol,
declare all state and operations, and pass independent accounting preflight.

`DEV_SMOKE` output cannot be called an advantage, disadvantage, or scientific
result.

## 8. Forbidden changes

GRI-SC-0 and any later SC unit may not:

- change fixtures, labels, splits, delays, decoder rules, precision rules,
  serialization, or verdict logic;
- increase state width, parameter ceiling, or operation ceiling;
- add gates, memory vectors, counters, clocks, phase variables, history,
  routing, geometry, or task-specific state;
- pass task, fixture, delay, label, or sequence metadata to the candidate;
- treat the finite-state oracle as an opponent;
- use a post-result change to rescue a failed candidate;
- issue a scientific verdict.

## 9. Success and failure logic

The lower-bound artifact may produce exactly one of:

```text
SELECTOR_COST_LOWER_BOUND_PROVED
    Under the declared model, preserve/transform semantics require at least
    one additional discrimination operation beyond the 97-operation ceiling.

SELECTOR_COST_LOWER_BOUND_DISPROVED
    A fully specified admissible construction fits within the existing 97
    recurrent-operation ceiling. This is not yet a scientific result.

SELECTOR_COST_LOWER_BOUND_INCONCLUSIVE
    The declared model does not settle the question.
```

`DISPROVED` may justify a separate request for GRI-SC-1 development search.
`INCONCLUSIVE` may also justify such a request if the lower-bound route cannot
be completed, but this contract does not authorize that search automatically.
A `PROVED` result closes the selector-cost question under its declared
assumptions without authorizing a wider architecture.

## 10. Future sequence

```text
GRI-SC-0  specification-only contract and lower-bound analysis
    ↓
GRI-SC-1  bounded DEV_SMOKE search, only if separately authorized
    ↓
GRI-SC-2  freeze one candidate and all hashes, only if warranted
    ↓
GRI-SC-3  one scientific run, only after separate authorization
```

At every transition, the existing scientific ledger remains unchanged until a
new frozen scientific run is independently authorized and completed.

## 11. Current state

```text
GRI-01:    CLOSED — BOUNDED NEGATIVE
GRI-02A:   COMPLETE — CONTRACT REPAIR
GRI-02B:   COMPLETE — EXECUTABLE PREREGISTRATION
GRI-02C:   ALGORITHMIC FINDING SUPPORTED; FORMAL ADVANTAGE REVOKED
GRI-02C.1: CLOSED — GRI02_NO_ADVANTAGE
GRI-SC-0:  SPECIFICATION-ONLY; NO CANDIDATE AUTHORIZED

MINIMALITY: NOT ESTABLISHED
LOWER BOUND: NOT YET ANALYZED
SUCCESSOR:  NOT AUTHORIZED
```
