# GRI-02-AUTHORIZATION-CONTRACT

**Status:** SPECIFICATION ONLY — IMPLEMENTATION NOT AUTHORIZED

**Revision:** GRI-02A — control-role repair

**Parent:** closed GRI-01 diagnostic sequence

**Purpose:** define the minimum gate a future preserve/transform primitive must
pass before any GRI-02 implementation is accepted.

This document authorizes no code, mechanism, training run, or architecture
change. It fixes the comparison and failure rules first.

## 1. Claim under test

A candidate digital cell can preserve task-relevant state across semantic
no-op recurrence and intentionally transform that state on an event, with:

- a bounded persistent state;
- bounded numerical precision;
- one time-invariant semantic interpretation;
- no larger parameter or per-step operation budget than the frozen parent;
- a reproducible advantage over the failed GRI-01 tanh cell, the stateless
  baseline, and the required mechanism ablations. The explicit finite-state
  control is a solvability oracle and lower-bound reference; matching it is
  allowed and does not by itself remove candidate credit.

The claim is not that the candidate is intelligent, biological, conscious, or
generally capable.

## 2. Non-negotiable containment

The future unit must remain inside `gri-research` and must not modify:

- the frozen WORLD-0 parent;
- GRI-01 code, configurations, fixtures, or receipts;
- the GRI-00 or GRI-01 mathematical specifications;
- any language model, agent framework, human experiment, or external service.

No mechanism is selected by this contract. A gate, latch, identity branch,
discrete register, or other design is admissible only if it satisfies the
same budget and evidence rules below.

## 3. Frozen resource budgets

The reference parent is the exact GRI-01 `d=8` cell:

```text
state budget:       8 persistent scalar slots
trainable parameters: 170 maximum
per-step state work: at most one 8x8 state transform,
                     one input-state injection,
                     and eight elementwise nonlinear operations
```

The candidate must report, before execution:

- every persistent state slot and its precision;
- every trainable and fixed parameter;
- every per-step multiply-add, comparison, lookup, copy, and nonlinear
  operation;
- every serialization field;
- all external inputs and outputs.

It fails the authorization gate if it exceeds any parent budget, hides state
in a counter, history buffer, lookup table, random seed, task label, or
decoder-side phase variable, or uses a step clock to replace recurrence.

The candidate must also use strictly less state/parameter/operation machinery
than a matched generic gated recurrent unit at the same state width. The
matched GRU counts must be recorded from the same input alphabet and counting
convention before the candidate run.

## 4. Required semantics

The candidate must expose two auditable transition classes:

```text
PRESERVE:  a semantic no-op leaves task-relevant distinctions invariant
TRANSFORM: an explicit event changes the intended field and preserves
           unrelated task-relevant fields
```

The implementation may realize these classes in any form, but the evaluator
must be able to identify which transition was requested without inspecting
hidden implementation state.

### Preserve fixtures

Reuse the GRI-01 delayed-bit, correction, and order tasks with the same
alphabet and labels. Evaluate semantic no-op delays:

```text
WAIT^N, N ∈ {0, 1, 2, 4, 8, 16, 32, 64, 128}
```

One fixed decoder per task must produce the correct answer at every `N`; a
wait-specific decoder is not admissible evidence of preservation.

### Transform fixtures

Use event-after-delay sequences, frozen before implementation:

```text
SET(A), WAIT^N, CORRECT(B), WAIT^M, QUERY
SET(A), WAIT^N, SET(B),     WAIT^M, QUERY_ORDER
```

with `N,M` drawn from the same delay set. The event must update the intended
fact, while any separately tested retained fact remains unchanged.

## 5. Precision and robustness gate

The candidate must be evaluated without post-result precision selection in:

```text
float64, float32, float16, bfloat16,
and symmetric hidden-state quantization at 8 bits.
```

For every preserve and transform fixture, the candidate must have:

- accuracy `1.0` at every registered delay;
- finite scores and states;
- a single fixed semantic decoder per task;
- strictly positive normalized geometric margin at every delay;
- no opposite-label state separation collapse below `0.5` of its `N=0`
  separation in float64;
- no label merge after 8-bit quantization.

The normalized margin is:

```text
minimum signed distance / ||w||
```

If the candidate fails float16, bfloat16, or any stress precision while
passing float32 and 8-bit quantization, the result is reported as a bounded
stress failure, not silently repaired or re-tuned. Failure of float32 or
8-bit quantization is an authorization failure.

## 6. Required controls and ablations

Every run must include the following comparison roles:

1. **parent opponent:** the unchanged GRI-01 `d=8` parent, which the
   candidate must beat;
2. **oracle/reference:** the explicit finite-state control from GRI-01D,
   which may match the candidate and establishes fixture solvability;
3. **baseline opponent:** the matched stateless baseline, which the candidate
   must beat on recurrence-dependent fixtures;
4. **no-preserve ablation:** route semantic no-op inputs through the ordinary
   transform path;
5. **no-transform ablation:** force event inputs through the preserve path;
6. **no-recurrence ablation:** remove persistent state;
7. **phase-readout prohibition:** reject wait-specific decoders.

The candidate receives credit only if the preserve mechanism is causally
necessary: removing it must fail a pre-registered long-delay preservation
criterion while the full candidate passes. The transform ablation must fail
the event-update criterion. If an ablation matches the candidate, the claimed
mechanism receives no credit. The finite-state oracle is exempt from this
opponent rule: it is expected to match or exceed the candidate and is used to
reject invalid fixtures or implementation failures.

## 7. Deterministic execution rules

Before implementation, freeze:

- input alphabet and exact fixtures;
- train/test delay sets;
- state and parameter budgets;
- precision and quantization rules;
- decoder definition and margin thresholds;
- seeds, optimizer, epoch/iteration limits, and stopping rule;
- serialization format and restart checkpoints;
- verdict logic and artifact hashes.

After the first result:

- no optimizer, dimension, precision, fixture, decoder, or threshold tuning;
- no mechanism additions;
- no post-result task removal;
- no manual repair of failed rows.

The receipt must contain implementation, configuration, fixture, control,
ablation, environment, and result hashes, plus a deterministic replay result.

## 8. Verdict logic

```text
GRI02_ADVANTAGE
    preserve and transform gates pass in float64, float32, and 8-bit;
    fixed semantic decoders pass all registered delays;
    all controls/ablations behave as pre-registered;
    budgets and replay pass.

GRI02_NO_ADVANTAGE
    the candidate fails a required gate, or the unchanged GRI-01 parent,
    stateless baseline, or a required mechanism ablation passes equivalently,
    or the preserve ablation receives no causal credit. Matching the explicit
    finite-state oracle/reference does not trigger this verdict.

GRI02_INCONCLUSIVE
    harness, replay, serialization, or environment failure prevents inference.
```

Only `GRI02_ADVANTAGE` permits a later successor unit. Any other result
closes the candidate without adding complexity.

## 9. Current authorization state

```text
GRI-01: CLOSED — BOUNDED NEGATIVE RESULT
GRI-02: NOT AUTHORIZED FOR IMPLEMENTATION
NEXT VALID ACTION: freeze an executable config and fixture receipt
                  against this contract, then seek a separate implementation
                  authorization. The next unit is GRI-02B — EXECUTABLE
                  PRE-REGISTRATION; it must contain no candidate code.
```

The earned design requirement is therefore:

> Preserve task-relevant distinctions across recurrence with bounded state,
> bounded precision, and a time-invariant semantic interpretation, while
> allowing explicit events to transform the intended state.
