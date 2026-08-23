# GRI-01H — Information-Location Diagnostic

## Claim under test

For the exact frozen GRI-01E `d=8` solution, the task answer is either
available in the pre-query hidden state through a time-invariant linear
separator, available only through a wait-specific phase-dependent separator,
or lost when recurrence collapses distinct task states.

No GRI parameters were retrained or changed. Linear separators are post hoc
measurements over the hidden states, fit independently for each task because
the task-specific query supplies task context.

## Check

The harness records the pre-query hidden state for every unique training case
at `WAIT 0` through `WAIT 32`. It then tests:

1. opposite-label Euclidean separation at every wait count;
2. one fixed linear separator over all cases and all wait counts for each task;
3. one separate linear separator at each wait count for each task.

Separators are checked by deterministic `scipy.optimize.linprog` feasibility
with signed margin `y · (w·h+b) >= 1.0`.

## Verdict

```text
PHASE_LOCALIZED_LOSS
```

All three tasks fail the fixed-separator test, but each remains perfectly
decodable by wait-specific separators for an initial phase window before
eventual state collapse.

| Task | Fixed separator | Perfect wait-specific phases | Final opposite-label separation |
|---|---:|---|---:|
| correction | infeasible | `0–24` | `1.0877e-12` |
| delayed bit | infeasible | `0–25` | `3.2053e-12` |
| order | infeasible | `0–28` | `4.6549e-11` |

Initial opposite-label separations were `1.9998` (correction), `4.4688`
(delayed bit), and `5.0500` (order). The long-delay values are effectively
collapsed to one hidden state, matching GRI-01F.

## Criteria

- Fixed decoder across the full horizon: **FAIL** for correction, delayed bit,
  and order.
- Phase-local decoder: **PASS** for phases listed above; **FAIL** after those
  windows.
- Hidden-state recording: **PASS**; all cases and 33 wait counts are in the
  machine-readable receipt.
- Architecture unchanged: **PASS**; only post hoc decoder measurements were
  added.
- Deterministic replay: **PASS** after ignoring only `timestamp_utc`.
- Existing regression suite: **PASS**, 30 tests.

## Interpretation and credit assignment

The result separates two failures that GRI-01G combined:

- At early phases, delayed-bit and correction states are linearly separable
  even when the original query/readout is wrong. Their information is present,
  but the frozen query/readout is not aligned with it at every phase.
- No single decoder remains valid over the full trajectory, so the code is
  phase-dependent rather than invariant.
- After approximately 25–29 waits, opposite-label states become numerically
  indistinguishable. That is genuine information loss, not only a readout
  mismatch.

The bounded conclusion is therefore: **phase-dependent coding followed by
state collapse**. A protected-state mechanism is not tested or authorized by
this unit; the evidence only identifies a future requirement for separating
semantic state from elapsed-time phase.

## Assumption register

- **Verified:** the parent GRI-01G configuration hash matches the frozen
  parent recorded by H.
- **Verified:** the exact deterministic GRI-01E solver and `d=8` parameters
  are reused.
- **Verified:** no optimizer, dimension, transition, readout, or task fixture
  was changed.
- **Checkable but bounded:** linear separability is an in-sample diagnostic on
  the finite fixture cases, not a generalization claim.
- **Unfalsifiable here:** whether a different learned representation could
  preserve the same semantics without architectural additions.

## Verification gap

This unit does not test a new cell, repair the current cell, or establish a
general theory of digital memory. The LP decoder is a diagnostic and does not
prove nonlinear or out-of-fixture information content.

## Stop / continue

Stop this diagnostic. Do not add protected memory, geometry, agents, or new
dimensions. The next design, if authorized later, must explicitly compare a
preserve/transform mechanism against this exact frozen parent and ablate it.

## Evidence

```text
config SHA-256:         4ae3f5aebfa9aeb25ddd91f2a371dd24277e4503e689d51a9f732ee557aa7efa
implementation SHA-256: f979a96559a93632db98172c421574c18d4626108b1b0b7c1a1c82558c746c4f
receipt SHA-256:        c4fa21a2673c710f93826e08f14c0f3bf6e9d52f7906578599a3b703237b921b
replay:                 PASS
```
