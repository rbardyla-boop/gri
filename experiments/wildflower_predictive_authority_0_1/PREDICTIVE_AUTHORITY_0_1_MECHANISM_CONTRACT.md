# Predictive Authority 0.1 — Mechanism Contract

## Scope

This contract covers only the predictor/null authority boundary. The
Dual-Authority-0.3 provenance and belief-revision subsystem is a frozen
downstream consumer and is not reimplemented here.

## Components

At each rollout origin the system constructs:

```text
N = transparent velocity-null proposal
L = learned predictor proposal
G = N + authority * (L - N), clipped to the state bounds
```

The learner receives only sensor-derived state and action IDs. The authority
policy receives machine-native pre-truth signals through `AuthorityContext`.
There is no natural-language path.

The authority context deliberately has no target, truth, event, or evaluator
error field. The oracle policy is implemented as a separate evaluator-only
function and cannot be passed to the mechanism rollout.

## Policy identities

`P0_NULL_ONLY` sets authority to zero. `P1_LEARNED_ONLY` sets it to one.
`P2_CURRENT_POLICY` carries the historical scalar authority and decay.
`P3_DELAYED_AUTHORITY` delays the scalar signal by one rollout step.
`P4_CAPPED_AUTHORITY` applies the fixed diagnostic cap of 0.65.
`P5_HORIZON_AWARE_DIAGNOSTIC` applies fixed horizon factors of 1.0, 0.55,
and 0.35 for H1, H8, and H32. `P6_ORACLE_UPPER_BOUND` is evaluator-only.

The single scientific candidate is `HORIZON_CONDITIONED`, exactly the factor
schedule above. `DISAGREEMENT_GATED` is retained only as a diagnostic
comparator. No policy is selected after seeing seed 360.

Base authority is `clip((innovation_score - 0.30) / 0.30, 0, 1)`. For a
requested horizon H, the candidate uses one origin factor `f(H)`:
`f(1)=1.00`, `f(8)=0.55`, and `f(32)=0.35`. At rollout offset k the applied
authority is `clip(base_authority * f(H) * 0.998**k, 0, 1)`. Factors apply once
per origin, not recursively as a newly estimated signal. Hidden state starts
at zeros after a 12-step observed burn-in.

## Rollout isolation

Null, learned-only, and gated paths are advanced separately from the same
origin state. The gated path's recurrent model state is driven by its own
gated prediction; the learned-only path is driven by its own learned
prediction. The null path is driven by its own velocity-null state. This makes
recursive divergence visible instead of inferring it from a single mixed
trajectory.

Each `RolloutStep` records all three predictions and evaluator-only target/error
fields. Every H1/H8/H32 origin contains exactly the requested number of steps.

## Serialized rollout-step field contract

The producer and evaluator share one exact serialized field contract. The three
local error fields are:

```text
null_local_error_evaluator_only
learned_only_local_error_evaluator_only
gated_local_error_evaluator_only
```

`learned_local_error_evaluator_only` is a retired alias. A serialized rollout
step containing that alias, missing the canonical field, or containing an
unknown field must fail closed. The producer validates its own serialized
payload, and every gate consumer validates the payload before reading errors.
This prevents a producer/classifier spelling drift from becoming an
operational failure at result assembly.

## Candidate behavior requirements

Candidate mechanisms must:

- defer to NULL_ONLY when learned evidence is unreliable;
- retain positive authority when learned rollouts are useful;
- avoid using event truth or future target information;
- avoid permanent authority collapse;
- preserve H1 and H32 behavior while addressing H8 recurrence;
- remain deterministic under `PYTHONHASHSEED=0` and one-thread settings.

## Exact successor gates

The complete arithmetic is in the scientific gate table. The two nontriviality
quantities are explicitly:

```text
origin_h8_authority = mean(authority[0:8])
fraction = count(origin_h8_authority > 0.10) / count(eligible origins)
mean_all = mean(origin_h8_authority across ALL eligible origins)
```

The candidate passes this gate only when `fraction >= 0.05` and
`mean_all >= 0.05`. Empty populations fail.

## Artifact and failure rules

The runner must record model, selectors, source hashes, traces, policy names,
runtime, and semantic receipt. Invalid JSON, missing horizons, NaN/Inf,
nondeterministic replay, or a seed-guard violation is an operational failure,
not a scientific FAIL. No scientific seed is authorized by the current package.
