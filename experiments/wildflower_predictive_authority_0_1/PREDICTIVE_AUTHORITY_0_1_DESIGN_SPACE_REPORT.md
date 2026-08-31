# Predictive Authority 0.1 — Design-Space Report

## Evidence carried forward

The local cross-seed autopsy found:

- 311 and 340: repeated mode-1 H8 failures where learned-only H8 was worse
  than null and authority was high;
- 320-R3: a distinct, tiny mode-0 boundary miss with low authority;
- event-H8 did not explain the mode-1 failures;
- finite deterministic replay reproduced the recorded 0.2/0.3 ratios;
- the epistemic/provenance metrics and scaling repair passed in 340-R1.

The historical 0.3 artifact does not contain learned-only H8 trajectories or
full policy counterfactual state. That absence is the reason the successor
serializes all three recursive paths from every origin.

## Design alternatives

### A. Calibrated scalar

This keeps one authority signal and changes its calibration. It is attractive
for simplicity, but the current evidence is horizon-specific: a local signal
can be useful while recursive H8 is unsafe. Scalar calibration remains a
diagnostic baseline, not a chosen successor.

### B. Horizon-conditioned authority

This gives H1, H8, and H32 separate authority factors. It directly tests the
observed mismatch between local usefulness and recursive rollout reliability.
It is frozen as the primary candidate because it addresses the failure's
specific horizon without touching epistemic semantics.

### C. Disagreement/uncertainty gating

This lowers authority when the learned trajectory diverges from the
transparent null using pre-truth model/state signals. It is selected because
the null is a real competitor and the failure episodes show learned H8 worse
than null before final gating.

### D. Predictor representation change

This remains a possible later outcome. The present diagnostics cannot justify
changing the predictor representation before learned-only recursive traces are
available. The successor therefore instruments the predictor first.

### E. Abandon learned authority

NULL_ONLY is retained as a control and safety fallback. Abandonment would be a
scientific conclusion only if fresh preregistered evidence shows no useful
nontrivial authority regime, not a design assumption.

## Chosen design space

The diagnostic harness includes P0–P6 and `DISAGREEMENT_GATED`, but exactly one
primary scientific candidate is frozen:

1. `HORIZON_CONDITIONED`.

The current policy, delayed signal, capped signal, P5 structural diagnostic,
disagreement gating, and evaluator oracle remain comparison points. The oracle
is not implementable as a mechanism because it uses truth.

## Decision gate

After engineering diagnostics, exactly one recommendation must be made:

```text
A current policy sound
B scalar calibration repair
C horizon-aware repair
D disagreement/uncertainty repair
E predictor representation change
F abandon learned authority
```

The design-only recommendation is **C. HORIZON-AWARE REPAIR**: implement and
measure horizon conditioning first because the repeated historical failures
are specifically H8-localized. `DISAGREEMENT_GATED` remains the secondary
diagnostic candidate needed to separate horizon structure from model/null
disagreement. This is not a scientific claim that the candidate wins.

## Rejected shortcuts

- Tuning a threshold to make 1931950002 or 305037050000 pass is forbidden.
- Treating evaluator-side accounting as an independent policy is forbidden.
- Replacing the learned predictor with NULL_ONLY is not a repair.
- Using event locations, target error, or future state in authority is leakage.
- Reopening provenance semantics would confound a localized predictive defect.
