# WILDFLOWER Predictive Authority 0.1 — Preregistration

Status: design-only prelock. No scientific seed has been executed.

## Claim under test

A learned predictor should receive authority over a transparent velocity-null
only when machine-native evidence available at decision time indicates that the
learned proposal is sufficiently reliable for the requested rollout horizon.
The authority mechanism must preserve useful learned improvements without
turning a locally useful but recursively unsafe predictor into a worse-than-null
H8 or H32 forecast.

This is a successor question, not a re-analysis of 311, 320, or 340. Those
records are spent and may be used only for diagnostics and hypothesis
generation.

## Frozen history and boundary

Dual-Authority-0.3 seed 340-R1 remains frozen with artifact SHA-256:

```text
b62e89e515d741235d3d6bb4433f654af0fed6ef98aa56810c48e7253c1c84be
```

Its epistemic/provenance result remains outside this successor's intervention:
Metric A 132/132, Metric B 4571/4571, safety PASS, provenance PASS, scaling
PASS, predictive authority FAIL, overall MIXED.

No scientific execution is allowed for 341, 342, 350, or 351. The successor
reserves fresh development seeds 360–362 and qualification seeds 370–371, but
none is authorized in this pass. Selectors are disjoint from every historical
range.

## Scientific selectors and model

The successor carries the historical numeric predictor and Nursery world as
fixed comparability dependencies. It does not change:

- the Nursery world;
- model architecture or training loss;
- training and ordinary episode lengths;
- predictive gate definitions;
- epistemic semantics;
- controls or provenance code.

New selector namespace:

```text
model seeds:       360, 361, 362, 370, 371
selector root:     3,600,000
slot width:        200,000
range width:       49,999
```

Each scientific artifact records the exact selected episode seeds and source
hashes. The historical failure episodes are not selected by this namespace.

## Required observability

For every ordinary episode and every eligible rollout origin, the artifact
must serialize:

- null, learned-only, and gated H1 predictions;
- null, learned-only, and gated H8 trajectories;
- null, learned-only, and gated H32 trajectories;
- innovation score, authority, local null/learned-only/gated error using the
  exact serialized fields defined in
  `PREDICTIVE_AUTHORITY_0_1_MECHANISM_CONTRACT.md`;
- rollout origin, evaluator-only event location, and clipping information;
- per-step authority and prediction vectors within each rollout.

The target and error fields are evaluator-only and are named as such. They are
never inputs to an authority policy.

## Frozen primary scientific candidate

The only primary scientific candidate is `HORIZON_CONDITIONED`. It is exactly
the former P5 structure, now frozen as a mechanism rather than a family:

```text
base_authority = clip((innovation_score - 0.30) / 0.30, 0, 1)
H1 authority  = clip(base_authority * 1.00, 0, 1)
H8 authority  = clip(base_authority * 0.55, 0, 1)
H32 authority = clip(base_authority * 0.35, 0, 1)
```

The factor is applied once at the rollout origin for the requested horizon;
the resulting authority is then multiplied by the unchanged historical
per-step decay `0.998**offset`. At every step the gated recurrent state is
advanced from its own prior gated state, while null and learned-only paths are
advanced independently. Initialization uses zero recurrent hidden state and
the unchanged 12-step burn-in. No event, target, future frame, or evaluator
error enters the mechanism.

The factors are a fixed structural schedule selected before fresh seed 360 to
test the hypothesis that recursive horizons should receive less learned
authority than one-step prediction: full H1 authority, approximately half H8
authority, and approximately one-third H32 authority. They are not fitted to
311, 320, or 340 and cannot be changed after observing a successor result.

## Counterfactual policy harness

The runner and engineering profile expose the following policies:

```text
P0  NULL_ONLY
P1  LEARNED_ONLY
P2  CURRENT_POLICY
P3  DELAYED_AUTHORITY
P4  CAPPED_AUTHORITY
P5  HORIZON_AWARE_DIAGNOSTIC
P6  ORACLE_UPPER_BOUND (evaluator-only)
```

P3–P5 and `DISAGREEMENT_GATED` are diagnostic comparators. P6 chooses the
lower-error component using evaluator truth and is never a mechanism
candidate. Only `HORIZON_CONDITIONED` receives the scientific successor
PASS/FAIL verdict. `DISAGREEMENT_GATED` remains a diagnostic comparator and is
not a second candidate.

## Mechanism questions and gates

The successor must report the old frozen gates for comparability:

```text
H1 max ratio <= 1.10
H8 max ratio <= 1.00
H8 mean ratio <= 0.90
H32 max ratio <= 1.00
H32 mean ratio <= 0.85
event-H8 mean ratio <= 0.90
```

The exact successor gates, denominators, equality rules, and zero-denominator
behavior are frozen in
`PREDICTIVE_AUTHORITY_0_1_SCIENTIFIC_GATE_TABLE.md`. In particular:

```text
H8 worse subset: learned_H8_error > NULL_H8_error
H8 useful subset: learned_H8_error < NULL_H8_error
useful capture: sum(NULL - gated) / sum(NULL - learned) >= 0.50
worse protection: sum(gated) / sum(NULL) <= 1.05
H1 global regression: sum(gated H1) / sum(NULL H1) <= 1.05
H32 global non-inferiority: sum(gated H32) / sum(NULL H32) <= 1.05
```

Each subset requires at least 30 origins; empty or zero denominators fail.
Negative captured gain remains negative and is not clipped. Equal learned and
null errors belong to neither subset.

For nontriviality, each origin's H8 authority is the mean of its eight
per-step authority values. The two exact requirements are:

```text
count(origin_mean_H8_authority > 0.10) / count(origins) >= 0.05
mean(origin_mean_H8_authority across ALL origins) >= 0.05
```

The evaluator also reports the four exact H8 classifications
`MODEL_GOOD_POLICY_GOOD`, `MODEL_GOOD_POLICY_HARMFUL`,
`MODEL_BAD_POLICY_PROTECTED`, and `MODEL_BAD_POLICY_HARMFUL`.

## Leakage and integrity rules

Authority policies may use only innovation, null/learned disagreement,
residual history, instability, saturation duration, state-change magnitude,
and recurrence sensitivity available before truth is revealed. They may not
use target state, evaluator error, event truth, future frames, or epistemic
labels.

Every artifact must pass finite-value validation, deterministic replay, source
hash stability, and selector/seed guard checks. A failed runner is operational
failure and produces no scientific verdict.

## Fresh-seed plan

No seeds are run during this design pass. After an independent prelock review:

```text
development:    360, 361, 362
qualification:  370, 371
```

The first fresh development run must be separately authorized and must not be
used to alter this preregistration after seeing its result.
