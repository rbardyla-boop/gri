# WILDFLOWER Dual-Authority-0.1 preregistration

Status: **LOCAL PRE-LOCK ONLY; QUALIFICATION IS NOT AUTHORIZED**

## Historical boundary

Dual-Authority-0, model seed 310, its frozen files, authorization, and scored
receipt remain immutable historical evidence. The frozen scientific verdict is
`EPISTEMIC_AUTHORITY_FAILED`. This successor does not revise that verdict and
does not rerun seed 310.

## Question

Does the two-authority design pass when continuous alternate-support
preservation is measured separately from correct grounded recomputation after
parent claim values change?

The successor must distinguish:

- preservation of an existing valid support path; and
- replacement of invalidated provenance with a new world-rooted support.

## Frozen metric definitions

### Metric A: `alternate_support_preservation`

An opportunity requires all of the following:

1. The derived packet value is correct before the witness.
2. At least one effective support in its transitive support lineage is
   invalidated by the witness.
3. The original derived support remains effective.
4. Every parent claim key used by that support remains committed through an
   independent world-rooted path.
5. The claim remains committed before grounded recomputation runs.

Success is an opportunity for which the claim remains committed without a new
derived support being inserted.

### Metric B: `recomputed_after_parent_change`

An opportunity requires all of the following:

1. The derived packet value is correct before the witness.
2. One or more original parent claim keys are invalidated.
3. The original derived support becomes ineffective.
4. Corrected world parents imply the same or a changed derived value.

Success requires stale support to remain ineffective, a new derived support to
cite corrected parent keys, and the reconstructed claim to have the expected
grounded status after recomputation.

## Additional measurements

The pre-lock harness records:

- `stale_support_survival_rate`: invalidated derived support paths that remain
  effective divided by invalidated derived support paths;
- `false_durable_claim_rate`: false committed values divided by evaluated truth
  slots;
- `rollback_recall`: contradicted prediction claims revoked divided by
  contradicted prediction claims;
- `recomputation_precision`: correct reconstructed derived claims divided by
  reconstructed derived claims;
- `recomputation_recall`: successful reconstructions divided by eligible
  recomputation opportunities;
- `duplicate_support_rate`: duplicate support signatures divided by all support
  insertions;
- `orphan_support_rate`: enabled derived supports with missing parent claims
  divided by enabled derived supports;
- `support_DAG_integrity`: cycle-free graph with an exact reverse child index;
- `active_store_bound`: active claims never exceed 8,192;
- `deterministic_replay`: numeric ledger replay hash equals its append hash.

The support graph retains disabled support records for provenance inspection;
it fails closed on capacity rather than evicting records that descendants may
still reference.

## Controls

The retained controls are `DIRECT_COMMIT`, `CONFIDENCE_COMMIT`,
`DAG_NO_WITNESS`, and `WITNESS_NO_DAG`. The successor also specifies
`WITNESS_PLUS_RECOMPUTE_NO_DAG` and `DAG_PLUS_WITNESS_NO_RECOMPUTE` to separate
the contributions of witnessing, dependency tracking, and recomputation.

## Fresh seed roles and disjoint selectors

- development/mechanism shakeout: model seeds `311`, `312`, `313`;
- untouched qualification: model seeds `314`, `315`;
- spent and excluded: seed `310` and all historical seeds listed in
  `design.py`.

Selector ranges are deterministic and disjoint. Seed 310 used starts
600,000/650,000/700,000. Successor starts begin at 800,000 and allocate a
separate 200,000 block per model seed.

Roles, thresholds, controls, selectors, and gates must be frozen before any
qualification execution.

## Proposed qualification gates

The qualification set must satisfy, per aggregate and per untouched seed where
specified:

- at least 30 Metric-A opportunities and exact preservation rate `1.0`;
- at least 30 Metric-B opportunities, precision `1.0`, and recall `1.0`;
- stale-support survival rate `0.0`;
- false durable claim rate `0.0`;
- rollback recall `1.0`;
- duplicate and orphan support rates `0.0`;
- support-DAG integrity, active-store bound, and deterministic replay all true;
- controls demonstrate that witnessing, dependency tracking, and
  recomputation each have an identifiable role.

These are proposed gates only. They are not qualification authorization.

## Pre-lock stop condition

This experiment must stop after static checks, deterministic micro-simulations,
regression tests, contamination review, and the local pre-lock report. Seeds
314 and 315 must not run until that report is reviewed and a separate local
authorization is created.
