# WILDFLOWER-0 / Nursery-1 pre-lock findings

Status: engineering shakeout only. The authority successor has now cleared a fresh hosted replication/promotion gate, but architecture freeze and `PRIMITIVE-0` remain separately unauthorized.

## Why Nursery-1 exists

Nursery-0 exposed two opposite failure modes: a direct pixel model could beat the one-step copy baseline but compounded badly, while a recurrent multi-horizon model flattened its long-horizon curve by collapsing into a stable bad predictor. A harder world was needed before any architecture lock.

Nursery-1 therefore adds three persistent objects, autonomous motion, boundary interactions, collisions, a one-step delayed controlled action, and an episode-level hidden dynamics mode. The hidden mode and interaction flags are evaluator-only. Learner-visible data remain numeric pixels, waveform samples, and machine action IDs.

## Precursor shakeout receipts

The following were exploratory engineering runs. None authorize an architecture claim.

### N1-A — learned per-channel EMA state, fresh seeds 60-62

The candidate beat the copy baseline on seeds 60 and 61, but seed 62 failed the one-step gate:

- seed 60 one-step ratio: 0.528; h32/h1 growth: 2.58x
- seed 61 one-step ratio: 0.612; h32/h1 growth: 2.34x
- seed 62 one-step ratio: 1.151; h32/h1 growth: 2.23x

Result: `CANDIDATE_FAIL`. Long-horizon stability alone was insufficient.

### N1-B — explicit object-state delta scaffold, seeds 70-72

The first evaluator rendered predicted centroid states with a Gaussian while the world rendered crosses. A perfect target centroid therefore had a non-zero weighted-frame error floor of about 0.1075. This contaminated model-vs-frame-baseline comparison.

Result: `MEASUREMENT_INVALID_RENDERER_MISMATCH`. The seeds are preserved and not rescored as a valid qualification.

### N1-C — corrected hard-raster evaluator, fresh seeds 80-82

The scaffold remained stable at long horizon but failed to beat the one-step null on two of three seeds:

- seed 80 ratio: 1.363
- seed 81 ratio: 1.058
- seed 82 ratio: 0.958

Result: `STATE_DELTA_FAIL`.

### N1-D — adaptive recurrent state, fresh seeds 100-102

The recurrent model improved long-horizon error relative to constant-velocity extrapolation but degraded one-step prediction on all three seeds. This localized a tradeoff rather than a pass.

Result: `ADAPTIVE_RECURRENT_PARTIAL_ONLY`.

### N1-E — gated residual development, fresh development seeds 110-112

Position-MAE ratios versus the velocity null:

| seed | h1 | h8 | h32 |
|---:|---:|---:|---:|
| 110 | 1.102 | 0.927 | 0.775 |
| 111 | 1.062 | 0.617 | 0.613 |
| 112 | 1.000 | 0.733 | 0.595 |

This was the first strong evidence that learned residual dynamics could improve multi-step prediction while remaining close to the null at one step. It was development evidence only.

### N1-F — attempted fresh qualification, seeds 130-131, stopped early

The registered every-seed one-step non-inferiority gate was `<= 1.10`. The first two fresh seeds produced h1 ratios 1.151 and 1.334. Seed 131 also produced h8 ratio 1.00086. The conjunctive qualification was already dead, so remaining seeds were not opened for rescue.

During post-failure diagnosis, the training episode generator was found not to guarantee coverage of all hidden dynamics modes. For seed 130 the six training episodes covered modes `[1,1,1,1,1,0]`, while the held-out episode was mode 2.

This is an experiment-design defect: the intended question was cross-mode adaptation, but the training generator did not guarantee that every mode existed in the training cohort.

Result: `QUALIFICATION_FAIL_WITH_LATENT_MODE_COVERAGE_DEFECT`.

## Balanced-mode repair

The committed Nursery-1 instrument selects training and test episode seeds using a deterministic generator-only stratifier. It guarantees equal counts for modes 0, 1 and 2 while never exposing mode to the learner.

A balanced probe was then run with model seed 160 using two training and two test episodes per hidden mode. The residual model still failed the gates:

- h1 ratio mean 1.046; worst 1.179
- h8 ratio mean 0.933; worst 1.131
- h32 ratio mean 1.094; worst 1.455
- event-window h8 ratio mean 0.933
- all six conjunctive gates: FAIL

The important correction is that this failure can no longer be blamed on missing hidden-mode coverage.

## Innovation-triggered authority successor

The failure pattern suggested that the learned correction had useful information in some regimes but lacked a reliable right to override the transparent velocity null everywhere. The successor therefore separates **prediction** from **authority**.

The base prediction remains constant velocity. Recent learner-visible numeric prediction innovation is summarized over a 12-step history. With a frozen threshold of `0.30` cells and width `0.30`, that history controls a convex blend between the transparent null and the learned proposal. Open-loop learned authority decays by `0.998` per predicted step. Hidden mode and evaluator-only event flags are not inputs to the authority calculation.

Regression tests explicitly verify that changing evaluator-only mode metadata does not change the learner projection and that zero innovation gives the learned proposal zero external authority even when an adversarial model asks for full authority internally.

### Seed-190 fresh qualification

The candidate and authority constants were frozen before the fresh seed-190 qualification.

Result versus the velocity null:

| metric | mean | worst | gate |
|---|---:|---:|---:|
| h1 ratio | 0.9923 | 1.0575 | worst <= 1.10 |
| h8 ratio | 0.7446 | 0.9969 | mean <= 0.90; worst <= 1.00 |
| h32 ratio | 0.7823 | 0.9995 | mean <= 0.85; worst <= 1.00 |
| event h8 ratio | 0.7445 | 0.9969 | mean <= 0.90 |

All six core gates passed. The same learned model with the external authority boundary removed reached worst h1 ratio `1.4774`, demonstrating why a separate authority boundary was worth testing.

Seed-190 semantic receipt:

`44fd012e748897b20e5eb94998f33d7ba49fdc1af8439e0bd52a30520f001215`

Exact preserved artifact SHA-256:

`eec6229a4dae2f94917a8c942b64876e718386456c183332baa6a6b737fb66e0`

This was a qualification PASS, not yet a promotion.

## Preregistered replication 230

Before opening the fresh replication set, the candidate source, seed-190 receipt, authority constants, model seed `230`, generator offsets, six core gates, three simple transparent controls, and mechanism-credit margins were frozen in `AUTHORITY_REPLICATION_230_PREREGISTRATION.md` and `AUTHORITY_FREEZE_MANIFEST.json`.

The ordinary hosted pre-lock workflows were required to pass before a separate authorization-file commit could trigger the fresh run. The one-shot workflow verified the authorization parent SHA and all frozen source hashes before executing.

Fresh mode-balanced training/test episode IDs were generated only inside that authorized run. The exact runner then executed twice and produced byte-identical JSON output.

### Replication-230 result

| metric | mean | worst | gate |
|---|---:|---:|---:|
| h1 ratio | **0.9689** | **1.0338** | worst <= 1.10 |
| h8 ratio | **0.7817** | **0.9953** | mean <= 0.90; worst <= 1.00 |
| h32 ratio | **0.7969** | **0.9959** | mean <= 0.85; worst <= 1.00 |
| event h8 ratio | **0.7816** | **0.9952** | mean <= 0.90 |

All six core replication gates passed.

The preregistered transparent controls did not explain the effect. Their mean h8 ratio was about `1.02865` and mean h32 ratio about `1.00410`; the candidate beat the strongest simple control by more than the required `0.05` margin at both horizons. The ungated learned model again violated the one-step safety boundary with worst h1 ratio `1.45055`, while the authority-controlled candidate remained at `1.03377`.

Therefore all three preregistered mechanism gates also passed:

- `beats_best_simple_h8_by_0_05`: PASS
- `beats_best_simple_h32_by_0_05`: PASS
- `authority_restores_h1_safety`: PASS

Hosted result states:

- `replication_passed = true`
- `mechanism_credit_passed = true`
- `promotion_gate_passed = true`
- `primitive0_authorized = false`

Replication semantic receipt:

`a9795b32fe17fb9af71e48e6f23849995404c514b853e6d58b8fa0b51df72a54`

Exact canonical result-file SHA-256:

`9c0c742229c471ca55f170c5ffdb3abda014450782612b4aac17dc1e5da261a9`

Hosted artifact ZIP digest:

`2a5e71d8eedb66165e99072dc8292fc45c8d6948a0cf5115c9fab1a82692a3f6`

The surprise-injection suite remained descriptive only. It produced mean h8 ratio `0.6854` and mean h32 ratio `0.7884`; these values did not contribute to the registered promotion verdict.

## Current interpretation

1. Nursery-0 compounding error was real.
2. Stable low-information prediction can masquerade as good rollout stability.
3. A numeric object-state scaffold removes sparse-pixel and renderer ambiguity but does not by itself solve dynamics.
4. A learned residual can contain useful multi-horizon information while still being unsafe as the sole predictor.
5. Separating **what the learned model predicts** from **when it has authority to override a transparent null** survived a fresh mode-balanced hosted replication under fixed source bytes and fixed gates.
6. The positive result is currently evidence for this narrow mechanism in Nursery-1, not a claim about AGI, consciousness, general world modeling, or real-world superiority.
7. The experiment still uses an explicit object-centroid scaffold. Removing that scaffold remains a later and materially harder developmental-learning question.

## Next gate

Do not tune seed 230 or reopen the spent qualification sets.

The authority mechanism is now eligible for a separately reviewed `PRIMITIVE-0` gate because the preregistered promotion condition passed. Eligibility is not authorization: `PRIMITIVE-0` must remain unopened until its frozen representation exam, interfaces, baselines, and promotion semantics are re-read against the current WILDFLOWER objective and an explicit execution boundary is recorded.

The next action is therefore review/qualification of the already-frozen `PRIMITIVE-0` machine-native interchange instrument, not more Nursery-1 parameter search.
