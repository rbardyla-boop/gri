# WILDFLOWER-0 pre-lock findings

Status: **DO NOT FREEZE / DO NOT MERGE AS AN ARCHITECTURE CLAIM**

This package is an engineering shakeout only. It tests whether a very small world-first, tokenizer-free learner can survive basic implementation, replay, continual-learning, baseline, and compounding-error attacks before any architecture is locked.

## Invariants exercised

- random initialization only; no pretrained model;
- no tokenizer, transcript, LLM, CLIP, Whisper, RAG, or text labels in learner input;
- learner input is numeric pixels, raw waveform samples, and machine action IDs;
- evaluator-only identity metadata is physically outside model input;
- append-only episode history with SHA-256 hash chaining;
- bounded active-memory view over an accumulating history;
- deterministic seeds and replay checks;
- foreground-aware prediction metric so a blank frame cannot win by exploiting sparse pixels;
- comparison against a trivial copy-current-frame predictor;
- sequential-learning retention check;
- open-loop rollout checks at 1/4/8/16/32 steps.

## Defects found during shakeout

### 1. Packaging/import defect — fixed

The first pytest collection failed because the local package boundary was incomplete. `wildflower0/__init__.py` and explicit `PYTHONPATH` execution repaired the test environment. This was an implementation defect, not a model result.

### 2. Grounding evaluator defect — fixed

The first cross-modal score treated each individual audiovisual event as a unique class. Repeated encounters with the same object identity were therefore false negatives. The evaluator was replaced with an evaluator-only identity-prototype probe. Identity remains excluded from model training/input.

### 3. Sparse-pixel scoring loophole — fixed

Plain pixel MSE made an almost-blank reconstruction look deceptively good because most pixels are background. The metric was replaced with foreground-aware weighted MSE and a regression test proving that a blank foreground is penalized.

### 4. Single-latent design conflict — repaired, but not cleared

Forcing the complete visual latent to align with audio encouraged the visual encoder to retain shared identity semantics while discarding private state such as position. The representation was split into a shared semantic subspace and private state subspace, and a self-supervised frame reconstruction path was added.

This removed the earlier gross open-loop latent drift, but it exposed the stronger problem below rather than authorizing a pass.

## Preserved run A — latent/shared-private candidate

Fresh engineering seeds: `0,1,2,3`.

Receipt: `0a6c143c8bcc67cbd0e3cd2bc8e0015fd911bb9d68bb57571dc3b11f63ade04b`

What survived:

- all parameters finite;
- memory hash-chain integrity passed;
- 10,000-record memory stress retained the complete ledger while active view remained <=32;
- evaluator-only audiovisual grounding probe: mean `0.8678`, minimum `0.75` on a four-identity test (descriptive engineering signal only);
- 32-step rollout did not numerically explode under this representation.

What failed:

- mean one-step foreground-aware error: `0.08872`;
- mean trivial copy baseline: `0.07939`;
- mean model/copy ratio: `1.1806`; worst `1.5274`;
- sequential Phase-A forgetting delta reached `0.4727` on the worst seed, above the engineering gate.

Verdict: **FAIL PRE-LOCK**. A compressed latent system that loses to “copy the current frame” does not earn world-model credit.

## Preserved run B — bounded episodic replay repair

Fresh engineering seeds: `10,11,12`; no reuse of run-A seeds.

Repair: retain 64 old raw episodes during Phase-B learning and fit dynamics after a representation-stability phase.

Receipt: `1d70b77c48de3e9e49a1539cb4465c2070d4cb665e0a2ac1ac1f29a6a83abfbe`

Result:

- catastrophic forgetting was repaired in this small test: worst forgetting delta `0.0`, mean `-0.0091`;
- memory integrity and finite-value gates still passed;
- grounding signal remained above chance: mean `0.8507`;
- world-model baseline failure remained: mean model/copy ratio `1.1575`, worst `1.5162`.

Classification: **memory-mechanism repair succeeded; latent transition mechanism remains weak**.

## Preserved run C — direct pixel-dynamics alternative

Fresh engineering seeds: `20,21,22`.

This is a materially different implementation: action-conditioned convolutional sensor dynamics with no latent bottleneck in the transition path.

Receipt: `97f77dfad062e2ca6b9f3f091a630ac0edb1301c2c08bb1b5b652f02f3cdc294`

Result:

- one-step model/copy ratio mean `0.3837`, worst `0.5528`;
- therefore it decisively beats the trivial copy baseline on all three fresh seeds;
- however open-loop error compounds severely: 32-step / 1-step growth mean `15.97x`, worst `22.32x`.

Classification: **one-step sensor dynamics works; open-loop imagination is unstable**.

A separate deterministic-world isolation probe (object identity held fixed) still showed substantial long-rollout growth, so the compounding problem is not explained only by the toy world's unannounced object switches.

## Preserved run D — observation-corrected recurrent / multi-horizon candidate

Fresh engineering seeds: `40,41,42`. Deterministic identity is held fixed within each core rollout; unannounced identity switches are scored separately as surprise trajectories.

Receipt: `3eea837750427fd42d5a8256478eb34c766aa29d100e4d199e0d83c8b5e5245c`

This candidate separates observation correction from open-loop imagination and trains over eight-step rollout sequences. It also records a transparent kinematic control.

Result:

- numerical/open-loop stability improved: 32-step / 1-step growth mean `0.986x`, worst `0.999x`;
- but this stability is misleading because the model is already poor at one step;
- one-step model/copy ratio mean `2.278`, worst `2.836` -> **FAIL**;
- the transparent kinematic baseline is far stronger: model/kinematic one-step ratio mean `28.25x` worse.

Classification: **stable bad prediction is not a compounding-error solution**. The recurrent candidate appears to settle toward a low-information average state rather than learning the simple transition. This is preserved as a baseline/collapse failure, not promoted because its long-horizon curve is flat.

## Lint / test status

Current local package:

- `python -m compileall`: PASS;
- `pytest -W error`: **12 passed**;
- custom static checks: no tokenizer/LLM imports in cognitive core; no forbidden prose-routing fields; no tabs/trailing whitespace/>120-character style findings;
- finite-value checks: PASS;
- memory tamper injection: detected as intended.

`python -m pip check` reports a global environment conflict between installed `moviepy` and `Pillow 12.3.0`. WILDFLOWER imports neither package; this is an environment-level warning and must not be misclassified as a WILDFLOWER code failure.

## Current architecture verdict

Do not lock the model architecture yet.

The experiments localize two different issues instead of producing one vague “didn't work” result:

1. **Continual-learning interference:** bounded old-experience replay substantially repaired it in the tested seeds.
2. **Prediction-horizon tradeoff:** compressed latent dynamics is stable but loses a trivial one-step baseline; direct sensor dynamics beats the baseline but compounds badly in open-loop rollout; the tested recurrent multi-horizon repair removes growth only by becoming a poor predictor that loses both copy and kinematic controls.

That is enough evidence to reject a freeze but not enough evidence to reject the world-first/token-free thesis.

## Authorized next engineering gate

Build and compare, without changing these preserved results:

1. retire the tested recurrent candidate rather than tune seeds 40-42;
2. add an EMA/slow target encoder as a fresh representation-stability alternative;
3. test explicit object-centric state/delta prediction against the transparent kinematic control;
4. freeze a harder multi-object Nursery-1 world before scoring so a trivial frame shift is not the whole task;
5. keep deterministic trajectories and surprise-injection trajectories as separate rollout tests;
6. keep copy-frame, constant-frame, direct-pixel, and transparent kinematic controls;
7. execute the already-frozen `PRIMITIVE-0` machine-native representation exam only after a fresh candidate clears its pre-lock controls.

No architecture is promoted until a candidate beats its simple controls on fresh seeds without reopening the current seed sets for threshold tuning.
