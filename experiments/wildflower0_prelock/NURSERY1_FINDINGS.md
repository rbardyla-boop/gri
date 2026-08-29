# WILDFLOWER-0 / Nursery-1 pre-lock findings

Status: engineering shakeout only. Architecture freeze is blocked.

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

The committed Nursery-1 instrument now selects training and test episode seeds using a deterministic generator-only stratifier. It guarantees equal counts for modes 0, 1 and 2 while never exposing mode to the learner.

A balanced probe was then run with model seed 160 using two training and two test episodes per hidden mode. The residual model still failed the gates:

- h1 ratio mean 1.046; worst 1.179
- h8 ratio mean 0.933; worst 1.131
- h32 ratio mean 1.094; worst 1.455
- event-window h8 ratio mean 0.933
- all six conjunctive gates: FAIL

The important correction is that this failure can no longer be blamed on missing hidden-mode coverage.

## Current failure localization

1. Nursery-0 compounding error was real.
2. Stable low-information prediction can masquerade as good rollout stability.
3. A numeric object-state scaffold removes sparse-pixel and renderer ambiguity but does not by itself solve dynamics.
4. Learned residual dynamics show a repeatable multi-horizon signal in some modes/seeds.
5. The current residual model does not reliably know when to defer to the transparent velocity null.
6. Hidden-mode coverage must be stratified by the generator, even though mode remains forbidden learner input.

## Next gate

Do not tune the spent seeds.

The next successor should test an **innovation-triggered authority boundary** on fresh seeds: the learned residual is allowed to override the transparent null only when recent numeric prediction innovations justify that authority. The gate must be derived from learner-visible numeric history, not hidden mode labels. Compare it against:

- velocity-only null;
- residual model with no authority boundary;
- direct multi-horizon forecast control;
- surprise-injection trajectories kept separate from deterministic qualification.

Until that successor clears every preregistered mode-balanced gate, WILDFLOWER-0 remains pre-lock and `PRIMITIVE-0` stays unopened.
