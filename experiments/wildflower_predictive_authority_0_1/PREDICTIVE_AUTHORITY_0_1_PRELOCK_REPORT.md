# Predictive Authority 0.1 — Prelock Report

Status: design-only review package. No scientific seeds executed.

## Claim under test

The remaining WILDFLOWER blocker is the predictor/authority boundary. A
successor that records independent null, learned-only, and gated rollouts can
separate learned-model quality from authority-policy quality and test whether
authority should be horizon-conditioned or disagreement-gated.

## Prelock checks

- Separate package created under
  `experiments/wildflower_predictive_authority_0_1/`.
- Frozen 0.3 files are not imported as an active mechanism and were not
  modified.
- Historical numeric predictor and Nursery are fixed dependencies only.
- Historical seeds 311–351 are reserved; fresh selectors use the 3,600,000
  namespace.
- Scientific execution is fail-closed because no authorization file exists.
- Runner help is available.
- P0–P6 diagnostics and 14-case failure matrix are implemented.
- Trace contract requires complete H1/H8/H32 null/learned/gated paths.
- Oracle mixing is evaluator-only and is not a candidate mechanism.
- Exactly one primary candidate is frozen: `HORIZON_CONDITIONED`.
- `DISAGREEMENT_GATED` remains diagnostic-only.
- No scientific selector or fresh seed is used by the engineering profile.

Engineering evidence:

```text
profile: artifacts/engineering_profile.json
profile SHA-256: 5c3e31ab8bfb917af5083534a938c3e12559d6286efa3f6451d8e0a05d3b4653
frozen 340-R1 SHA-256: b62e89e515d741235d3d6bb4433f654af0fed6ef98aa56810c48e7253c1c84be
validation: 110 tests passed; compileall passed; Ruff passed
```

The profile contains the complete successor source-hash map and reports the
historical absence of learned-only H8/H32 fields. The exact scientific gate
table is in `PREDICTIVE_AUTHORITY_0_1_SCIENTIFIC_GATE_TABLE.md`.

## Verification criteria

The implementation must pass compileall, Ruff, and pytest with warnings as
errors. Engineering profile output must be finite, deterministic, and report
that no scientific seed was executed. The historical 340 artifact audit must
continue to identify the missing learned-only H8 fields, demonstrating that
the successor addresses the actual observability gap.

## Integration boundary

The frozen 0.3 epistemic machinery is a downstream fixed consumer only. A
later integration test may instantiate its in-memory Reference/Incremental
stores and compare their semantics, but predictive-authority diagnostics may
not change provenance, support identity, Metric A, Metric B, rollback, or
canonicalization.

## Expected later execution record

When separately authorized, each scientific result must include:

- exact command, seed, selectors, runtime, Python/numpy/torch versions;
- source hashes and semantic receipt;
- ordinary H1/H8/H32/event-H8 old gates;
- null, learned-only, gated errors and ratios at each horizon;
- full recursive trace with innovation, authority, events, clipping;
- counterfactual policy summaries and nontriviality gate;
- deterministic replay and finite-value validation;
- downstream epistemic integration result, without changing its semantics.

## Verdict

**PRELOCK DESIGN PASS, EXECUTION NOT AUTHORIZED.**

Decision-gate recommendation: **C. HORIZON-AWARE REPAIR**. The primary
candidate is frozen as the exact H1/H8/H32 factor schedule in the mechanism
contract. Disagreement gating remains a secondary diagnostic comparator. This
recommendation does not authorize any fresh seed.

The correct next action after independent review is to inspect the engineering
profile and source hashes. Do not run 360, 361, 362, 370, or 371 during this
pass. Do not modify 0.3 or the frozen scientific artifacts.

## Post-361 incident addendum

This addendum records the completed 361-R1 execution without rewriting its
artifact or converting it into a scientific result.

- Operational execution: PASS.
- Artifact structure: PASS.
- Scientific evaluator: INVALID.
- Scientific candidate verdict: NONE.
- Scientific interpretation: INCONCLUSIVE.
- Preserved artifact: `artifacts/development_seed361.json`.
- Preserved artifact SHA-256: `99f4663212dade718e39b10c2d1df66d49b7bd7f50653d69702fbb3b6b6e2113`.

The evaluator incorrectly implemented the frozen H8 useful-learner gate as
`capture_fraction <= 0.50`; the frozen rule is `capture_fraction >= 0.50`.
The observed `0.09203745816983593` was therefore incorrectly marked as a
pass. Raw diagnostics remain preserved, but no candidate judgment may be
drawn from 361-R1. The gate-direction audit is an engineering repair only;
it does not alter the candidate, formulas, thresholds, definitions, or
authorization state. 361-R1 remains permanently closed and must not be
rerun. No future scientific seed is authorized by this addendum.
