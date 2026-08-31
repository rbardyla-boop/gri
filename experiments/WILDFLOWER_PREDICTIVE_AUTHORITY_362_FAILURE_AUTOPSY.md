# WILDFLOWER Predictive Authority 362 Failure Autopsy

Status: engineering-only trace analysis. No scientific seed was run during
this autopsy. Seeds 360, 361, 362, 370, and 371 were not rerun or started.
The candidate, frozen gates, and scientific artifacts were read only.

## 1. Claim under test

The current `HORIZON_CONDITIONED` authority policy should capture at least
50% of available useful H8 learned improvement while protecting against
worse-than-null learned predictions. The autopsy asks whether the 362 failure
is caused by the predictor, authority allocation, recursive rollout behavior,
events, overconfidence, conservatism, or ordinary seed variance.

## 2. Evidence and observability

Inputs:

| run | artifact | SHA-256 | ordinary per-step observability |
|---|---|---|---|
| 311-R2 | `wildflower_dual_authority_0_1/artifacts/development_seed311.json` | `b51de9e7e7221c23226f95507fea4464446445fc9279d5e99398049c81e78c58` | no ordinary predictive trace; episode aggregates only |
| 340-R1 | `wildflower_dual_authority_0_3/artifacts/development_seed340.json` | `b62e89e515d741235d3d6bb4433f654af0fed6ef98aa56810c48e7253c1c84be` | H8-oriented trace rows and episode aggregates; no complete alternate policy rollouts |
| 362-R1 | `wildflower_predictive_authority_0_1/artifacts/development_seed362.json` | `41443ab8793ffed1f2caf04e1fa92187a08ac713db52b9d9cb3fa2a599b53854` | complete recorded H1/H8/H32 null, learned-only, and gated paths |

The separate 311 challenge replay was not substituted for missing ordinary
predictive traces. No target data was rehydrated and no runner was invoked.

## 3. Verdict

**The current predictive-authority mechanism fails, but the learned predictor
is not useless.** The best-supported diagnosis is a combination of:

1. context-dependent learned H8 quality;
2. insufficiently selective authority allocation; and
3. recursive H8 rollout interaction that magnifies a poor authority choice.

The epistemic/provenance subsystem is outside this failure. No candidate or
gate change is proposed here.

## 4. Cross-run measured evidence

Ratios are gated error divided by NULL error unless labelled learned-only.

| run / episode | mode | H1 current | H8 current | H32 current | event-H8 current | H8 learned-only | H8 authority | H8 innovation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 311 failure `1931950002` | 1 | 0.906429 | 1.038178 | 0.772412 | 1.038178 | 1.013993 | 0.907365 | 0.656448 |
| 340 failure `305037050000` | 1 | 0.916896 | 1.038211 | 0.688344 | 1.038211 | 1.125379 | 0.970346 | 0.681296 |
| 362 all six episodes, mean | — | 0.966272 | 0.954915 | 0.985293 | 0.954907 | 0.701416 | 0.344035 terminal mean | 0.535541 mean |

The two repeated failures share mode 1, H8-specific failure, learned-only H8
error above NULL, high authority in the fully observed 311/340 cases, and
nearly identical current H8 failure ratios. They do not share a universal
failure across every mode or seed.

For 362, the H8 pattern by mode is:

| mode | H8 learned-only ratio | H8 current ratio | terminal authority mean | useful-origin capture |
|---:|---:|---:|---:|---:|
| 0 | 0.994583 | 0.997115 | 0.041516 | 0.012249 |
| 1 | 0.605103 | 0.936218 | 0.478488 | 0.122607 |
| 2 | 0.457005 | 0.931369 | 0.512104 | 0.116746 |

The learner contains strong useful signal in modes 1 and 2, but the policy
does not convert that signal into sufficient H8 improvement.

## 5. Recorded-trace counterfactual diagnostics

The following 362 table reports mean episode ratios for H1, H8, H32, and
event-H8. `CURRENT_POLICY` is the recorded gated path. The other policies are
trace-only terminal-error blend diagnostics, not alternate recursive
rollouts:

- `NULL_ONLY`: recorded NULL error;
- `LEARNED_ONLY`: recorded learned-only error;
- `DELAYED_AUTHORITY`: recorded origin authority with one-step delay;
- `CAPPED_AUTHORITY`: recorded authority capped at `0.65`;
- `DISAGREEMENT_GATED`: a diagnostic proxy reconstructed from recorded
  prediction displacement where no clipping occurred;
- `ORACLE_UPPER_BOUND`: row-wise minimum of recorded NULL and learned-only
  errors, evaluator-only.

| policy | H1 | H8 | H32 | event-H8 |
|---|---:|---:|---:|---:|
| NULL_ONLY | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| LEARNED_ONLY | 1.049642 | 0.701416 | 0.613634 | 0.693550 |
| CURRENT_POLICY (recorded) | 0.966272 | 0.954915 | 0.985293 | 0.954907 |
| DELAYED_AUTHORITY (blend diagnostic) | 1.000000 | 0.717233 | 0.722449 | 0.717175 |
| CAPPED_AUTHORITY (blend diagnostic) | 0.979630 | 0.801962 | 0.796849 | 0.801904 |
| DISAGREEMENT_GATED (partial proxy) | 0.973662 | 0.723465 | 0.715409 | 0.723292 |
| ORACLE_UPPER_BOUND (evaluator-only) | 0.923292 | 0.605120 | 0.577453 | 0.604657 |

The disagreement proxy is available for 2,313 of 2,844 origins per horizon;
531 origins per horizon have clipping or insufficient information for exact
reconstruction. Its values are therefore diagnostic and not scientific
results.

On the H8 useful subset, available gain is `3767.437644302845` over 2,054
origins. Captured gain by trace-only diagnostic is:

| policy | captured gain fraction |
|---|---:|
| NULL_ONLY | 0.000000 |
| LEARNED_ONLY | 1.000000 |
| CURRENT_POLICY (recorded) | 0.105750 |
| recorded-authority terminal blend | 0.436939 |
| DELAYED_AUTHORITY blend | 0.796026 |
| CAPPED_AUTHORITY blend | 0.558313 |
| DISAGREEMENT_GATED partial proxy | 0.823342 on 1,836 useful origins |
| ORACLE_UPPER_BOUND | 1.000000 |

The recorded current path is materially worse than its terminal scalar blend
surrogate: pooled H8 ratio `0.950347` versus `0.827917`. This is evidence of
recursive state/rollout interaction, not proof that a scalar policy repair
will transfer unchanged to a fresh run.

For 311 and 340, the stored artifacts support NULL, learned-only, and current
episode-level comparisons, but not full delayed/capped/disagreement recursive
counterfactuals. Those values are recorded as unavailable rather than
manufactured.

## 6. Classification of the 362 harmful and protected cases

| classification | origins | mean H8 authority | mean H8 innovation | learned-only ratio | current-policy ratio |
|---|---:|---:|---:|---:|---:|
| MODEL_GOOD_POLICY_GOOD | 2,040 | 0.398017 | 0.576671 | 0.491717 | 0.946134 |
| MODEL_GOOD_POLICY_HARMFUL | 14 | 0.308399 | 0.512066 | 0.841471 | 1.009702 |
| MODEL_BAD_POLICY_PROTECTED | 696 | 0.206889 | 0.430717 | 1.418385 | 0.966443 |
| MODEL_BAD_POLICY_HARMFUL | 94 | 0.193303 | 0.422556 | 1.883251 | 1.010382 |

The policy protects 696 of 790 bad-model origins, but leaves 94 harmful. The
94 are not the highest-authority cases; their authority is close to, and
slightly below, the protected group while their learned error is much worse.
This is conditional overconfidence or poor uncertainty discrimination, not
simply global authority saturation.

The 14 good-model/harmful-policy cases are rare (`14/2054 = 0.68%`) but show
that even useful learned predictions can be damaged by the rollout policy.

## 7. Horizon and event analysis

The event subset does not explain the failure. In 362, current H8 is
`0.954915` overall and `0.954907` on event-H8 origins. In the repeated
failures, event-H8 equals H8 at the serialized episode level: `1.038178` in
311 and `1.038211` in 340.

The old mean gates fail because current 362 means are above their fixed limits:

- old H8 mean: `0.954915 > 0.90`;
- old H32 mean: `0.985293 > 0.85`;
- old event-H8 mean: `0.954907 > 0.90`.

H1 and H32 can pass in individual failure episodes while H8 fails, which
localizes the problem to recursive horizon behavior rather than a general
numerical collapse. No NaN/Inf or unbounded rollout evidence was observed in
the recorded 362 artifact.

## 8. Hypothesis assessment

| hypothesis | assessment | reason |
|---|---|---|
| A. predictor quality | **SUPPORTED, not sufficient alone** | Learned-only H8 is useful overall in 362 (`0.701416`) but worse than NULL in the 311 and 340 failure episodes and in 790 of 2,844 362 origins. |
| B. authority allocation | **SUPPORTED** | The policy fails to selectively trust useful predictions; 362 capture is only `10.57%`, while the harmful subset is not separated by authority magnitude. |
| C. recursive H8/H32 instability | **SUPPORTED** | Recorded current H8 is much worse than the terminal blend surrogate; H1/H32 can pass while H8 fails. |
| D. event-related effect | **NOT SUPPORTED** | Event-H8 tracks ordinary H8 in all three records. |
| E. authority overconfidence | **SUPPORTED in 311/340, conditional in 362** | Repeated mode-1 failures have authority means `0.907365` and `0.970346`; in 362 the issue is selective overconfidence, not globally high authority. |
| F. excessive conservatism | **SUPPORTED** | Current policy captures only `10.57%` of useful H8 gain despite 2,054 useful origins; delayed/capped blend diagnostics recover more. |
| G. ordinary seed variance | **CONTRIBUTOR, insufficient alone** | Other episodes pass, but the repeated mode-1/H8/high-authority pattern is too structured to call variance the sole cause. |

## 9. Repair decision

The next engineering direction should be:

**D. DISAGREEMENT/UNCERTAINTY REPAIR, with explicit horizon-aware rollout
instrumentation.**

Do not apply a global scalar calibration alone. Do not change the epistemic
subsystem, frozen gates, or current scientific artifacts. Do not abandon
learned authority: the learned-only control and oracle bound show real signal.

A successor design should serialize raw disagreement/uncertainty and complete
learned-only and alternate-policy recursive rollouts before any fresh
scientific authorization. It should test whether uncertainty can distinguish
the 94 harmful bad-model cases from the 696 protected cases and prevent the
14 good-model/harmful-policy cases without collapsing to NULL_ONLY.

## 10. Verification gaps and stop decision

- 311 lacks ordinary per-step predictive traces.
- 340 lacks complete policy-specific recursive H1/H8/H32 traces.
- 362 does not serialize raw disagreement, so its disagreement diagnostic is
  partial and proxy-based.
- A fresh independent seed is needed to establish whether the 362 pattern
  generalizes, but no seed is authorized by this autopsy.
- Transfer from this toy world to long-lived real agents is untested.

The autopsy is complete. No new candidate was selected or authorized. No
scientific seed was run. Stop here.
