# GRI-01 → GRI-02C.1 Synthesis

## Scope

This synthesis records the bounded Small-Info Primitive results from the
closed GRI-01 diagnostic sequence through the GRI-02C.1 accounting audit. It
does not authorize a successor mechanism.

The question was:

> What is the smallest executable digital primitive that can retain and
> transform useful state over recurrence?

This sequence does not establish that minimum. It establishes a bounded
mechanism requirement and exposes a one-operation resource-cost problem. No
minimum-state claim, operation lower bound, or minimality theorem has been
proved.

## Canonical sequence

| Unit | Result | What it established |
|---|---|---|
| GRI-01 | `NO_ADVANTAGE` | The frozen tanh recurrence did not beat the matched stateless baseline. This does not show that recurrence itself is useless. |
| GRI-01D | `CONTROL_PASS` | A tiny explicit finite-state recurrent control solved the fixtures, including held-out delays and serialize/restart checks. The tasks and recurrence requirement were valid. |
| GRI-01E | `PARTIAL_GENERALIZATION` | The frozen tanh cell had some representational capacity, but its learned solution did not robustly generalize the required transition. |
| GRI-01F | `CONTRACTIVE_MEMORY` | Required hidden-state distinctions collapsed toward a shared attractor under repeated `WAIT`. |
| GRI-01G | `TRANSIENT_CODING` | Short-delay success came from delay-dependent trajectories rather than a durable no-op state transition. |
| GRI-01H | `PHASE_LOCALIZED_LOSS` | No single time-invariant decoder worked across the horizon; wait-specific decoders remained feasible only while states were still separated. |
| GRI-01I | `PRECISION_FRAGILE` | The remaining mathematical separability disappeared much earlier under reduced representation precision. |
| GRI-02A | `COMPLETE` | The authorization contract was repaired so the finite-state control is an oracle/reference, not an opponent. |
| GRI-02B | `COMPLETE` | Fixtures, split, decoder protocol, q8 execution, serialization, operation rules, controls, and verdict logic were frozen before candidate code. |
| GRI-02C | Raw `GRI02_ADVANTAGE` | The identity-preserve candidate passed all raw task, decoder, precision, replay, and causal-ablation gates across three seeds. |
| GRI-02C.1 | Formal `GRI02_NO_ADVANTAGE` | The executable selector was internal and added one operation beyond the frozen resource ceilings. |

## What was learned

The GRI-01 failure was not a failure of recurrence as such. It was a failure
of a generic transform-at-every-step cell to preserve semantic state during a
no-op interval.

The authorized GRI-02C candidate used:

```text
WAIT       → h_next = h
other      → h_next = tanh(W h + E[token] + b)
```

Its raw result supports the bounded algorithmic finding that an explicit
`PRESERVE` / `TRANSFORM` distinction fixes this specific failure. Across all
three seeds it reached 100% on the 558-fixture bank, including 208 held-out
fixtures, with one fixed decoder per task. It passed float64, float32,
float16, bfloat16, and recurrent q8 evaluation. The required no-preserve,
no-transform, and no-recurrence ablations failed.

The result does not establish a general memory architecture, a digital
organism, cognition, or any broader theory.

## What was falsified or rejected

- Generic transform-every-step recurrence is not sufficient for the frozen
  long-delay preserve/transform family under the GRI-01 protocol.
- Short-delay accuracy is not evidence of persistent semantic memory.
- Mathematical separability without a bounded margin is not robust information.
- The raw GRI-02C run cannot claim formal resource advantage: its executable
  candidate performs `ids == self.wait_index` internally.

## Formal accounting closure

GRI-02B freezes comparison/branch-predicate cost at one operation. The audit
therefore charges the candidate selector as follows:

```text
parent recurrent ceiling:          97
candidate recurrent:         97 + 1 = 98

parent recurrent+query ceiling:   118
candidate recurrent+query:  118 + 1 = 119
```

The external-dispatch counterfactual would fit the ceilings, but it is not the
interface implemented by the frozen candidate. The formal result is therefore
`GRI02_NO_ADVANTAGE`, while the algorithmic mechanism finding remains
`SUPPORTED`.

## Remaining open question

The unresolved question is not whether explicit preservation can work. It can.
The unresolved question is:

> Can preservation be obtained without paying an additional explicit semantic
> selection operation, or is that cost unavoidable?

Possible answers include reallocating existing computation, making
preservation intrinsic to the transition rule, or proving a lower bound. None
is authorized by the current project state.

The original smallest-primitive question therefore remains open. The current
8-state, 170-parameter candidate and the explicit finite-state oracle are
constructive reference points, not proofs of minimality.

The selector-cost question is one lower-bound component of that same parent
question. It is not a change of project identity: the target remains the
minimum persistent state, transition machinery, and semantic-control cost
needed for reliable recurrent computation.

## Canonical boundary

```text
GRI-01:    CLOSED — BOUNDED NEGATIVE
GRI-02A:   COMPLETE — CONTRACT REPAIR
GRI-02B:   COMPLETE — EXECUTABLE PREREGISTRATION
GRI-02C:   ALGORITHMIC FINDING SUPPORTED; FORMAL ADVANTAGE REVOKED
GRI-02C.1: CLOSED — GRI02_NO_ADVANTAGE

SUCCESSOR MECHANISM: NOT AUTHORIZED
ADDITIONAL COMPLEXITY: NOT AUTHORIZED
```

## Evidence anchors

```text
GRI-02C raw receipt SHA-256:
6344a2a8240a7572ef0554a8b5bd2765fd9d64f676a293245fc3b8d75a622ebf

GRI-02C.1 audit receipt SHA-256:
6925d6347493503c38abe32dfbe367707246e752084b097a37109aa8a04fe957
```
