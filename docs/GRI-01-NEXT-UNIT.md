# GRI-01 — Smallest Executable Recurrence Unit

**Status:** EXECUTED; bounded result recorded in `GRI-01-NEXT-UNIT-RESULT.md`.

## Claim under test

A tiny fixed-dimensional state, updated by one transition rule reused at every
step, can retain and transform information across a delay or correction in a
way that a matched stateless baseline cannot.

This unit tests recurrence as a primitive. It does not test geometry,
language, agents, human cognition, or general intelligence.

## Minimal machine

For dimension `d ∈ {2, 4, 8}`:

```text
x_0 = fixed zero state
x_(t+1) = F_theta(x_t, input_t)       # the same F at every step
output  = R_theta(x_t)
```

The input alphabet, sequence grammar, state dimension, transition count, seed,
and readout are recorded in the experiment receipt. No external lookup table
or natural-language intermediate is permitted.

The matched ablation is a stateless readout receiving the current input and
the same parameter/count budget as closely as the implementation allows. A
second negative control may reset `x` at every step.

## Tasks

All tasks use held-out symbol combinations and held-out delay lengths.

1. **Delayed bit:** receive `BIT_0` or `BIT_1`, then `WAIT` for `N` steps,
   then report the stored bit.
2. **Correction:** store `A`, receive correction `B`, and report `B`.
3. **Order:** distinguish `A,B` from `B,A` at the final readout.
4. **Reset/restart:** serialize state, reconstruct the machine, continue the
   same sequence, and require byte-identical output to uninterrupted replay.
5. **Ablation:** rerun the recurrence-required tasks with recurrence removed
   or state reset each step; the result must expose whether recurrence was
   actually used.

## Acceptance and falsification

Before running, freeze the exact thresholds and seeds in the receipt. The
minimum proposed gate is:

- exact or pre-registered near-exact held-out accuracy for every dimension and
  delay condition;
- deterministic replay from the receipt;
- byte-identical restart continuation;
- no hidden side channel or task-specific lookup structure;
- a material, pre-registered recurrence-vs-stateless gap on tasks whose answer
  depends on delayed state.

The primitive claim is **not supported** if the stateless/reset baseline
matches the recurrent system, if performance collapses on held-out delays, if
the state is only a lookup table for seen sequences, or if restart changes the
output. A failure is a valid result and does not authorize adding memory,
geometry, language, or agents to rescue it.

## Required evidence

The eventual executable unit must emit:

```text
experiment specification hash
implementation hash
seed list
task/input fixture hash
per-task/per-delay results
stateless and reset ablation results
replay result
first failure, if any
```

The harness has now run and produced a bounded `NO_ADVANTAGE` result for this
unit. That result is not evidence that every possible GRI-01 formulation
fails, and it does not authorize adding complexity to rescue this run.
