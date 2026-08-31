# WILDFLOWER predictive-authority cross-seed autopsy

Local-only analysis of the completed 0.1 seed-311, 0.2 seed-320-R3, and 0.3
seed-340-R1 records. No scientific seed was run for this analysis. The frozen
scientific JSON files were read only and were not modified.

## Claim under test

The repeated H8 gate failures in mode 1 are evidence of a reproducible defect
in the predictor/authority path, rather than a provenance-store failure or
ordinary seed variance alone. The autopsy asks whether the defect is in the
learned predictor, authority allocation, H8 rollout, event handling, or their
interaction.

## Check

Audited artifacts and diagnostic records:

```text
experiments/wildflower_dual_authority_0_1/artifacts/development_seed311.json
experiments/wildflower_dual_authority_0_1/artifacts/seed311_autopsy_trace.json
experiments/wildflower_dual_authority_0_2/artifacts/development_seed320.json
experiments/wildflower_dual_authority_0_3/artifacts/development_seed340.json
```

Read-only checks performed:

- strict JSON parsing and recursive finite-value checks;
- artifact and receipt/hash inspection;
- comparison of serialized source hashes to current local sources;
- deterministic selector and seed-boundary inspection;
- comparison of every ordinary episode's H1/H8/H32/event-H8 metrics;
- recovery of H8 targets from the registered episode selectors to independently
  reproduce the serialized 0.2/0.3 H8 ratios;
- trace-only null, learned, actual, frozen-authority, one-step-delayed, and
  row-wise oracle counterfactuals;
- event-location, authority-saturation, innovation, clipping, and horizon
  trajectory summaries.

The 0.1 artifact has no ordinary per-step predictive trace. Its separate
diagnostic replay contains authority/innovation rows for the developmental
challenge, not the ordinary-test episodes. Those rows are not substituted for
missing ordinary-test traces.

## Verdict

**Overall verdict: FAIL for the current predictive-authority mechanism; the
epistemic/provenance subsystem remains outside the failure.**

The strongest supported diagnosis is **H: a combination of H8 learned-model
failure and authority over-allocation in mode 1, expressed through a
horizon-specific rollout interaction**.

This is repeated mechanism-level evidence, not proof that every mode-1 seed
will fail. Four other mode-1 ordinary episodes pass, so seed variance remains
a contributor. The repeated failure ratio and matching authority pattern are
too specific to treat the two failures as ordinary noise alone.

## Cross-run ordinary predictive results

The H8 `ungated` column is the learned/null error ratio. `H8 null`, `H8
learned`, and `H8 gated` are absolute H8 errors where available. For 0.2/0.3,
the H8 target and baseline were rehydrated from the registered episode seed;
the learned absolute error is the serialized ungated ratio multiplied by that
rehydrated null error. This is an engineering diagnostic, not a replacement
scientific result.

### Seed 311 / 0.1

| ordinary seed | mode | H1 | H8 | H32 | event-H8 | ungated H8 | H8 null | H8 learned | H8 gated |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1931950004 | 0 | 1.017332 | 0.996322 | 0.999437 | 0.996249 | 1.024551 | 2.431217 | 2.490906 | 2.422275 |
| 1931950006 | 0 | 1.023255 | 0.994483 | 0.994322 | 0.994147 | 1.004334 | 2.515873 | 2.526778 | 2.501992 |
| 1931950001 | 1 | 0.989970 | 0.800034 | 0.764738 | 0.800034 | 0.674763 | 3.486772 | 2.352746 | 2.789538 |
| **1931950002** | **1** | 0.906429 | **1.038178** | 0.772412 | **1.038178** | **1.013993** | 2.402116 | 2.435729 | **2.493825** |
| 1931950000 | 2 | 0.843414 | 0.781593 | 0.651891 | 0.781593 | 0.827858 | 3.753968 | 3.107754 | 2.934074 |
| 1931950005 | 2 | 1.041738 | 0.938284 | 0.678877 | 0.938284 | 0.982346 | 2.973545 | 2.921049 | 2.790031 |

The failure is ordinary seed `1931950002`, mode 1. Its H1 and H32 results
pass; H8 and event-H8 fail at the same value. The learned H8 error is already
above null before authority mixing, and the high-authority gated result is
worse still.

### Seed 320 / 0.2-R3

| ordinary seed | mode | H1 | H8 | H32 | event-H8 | ungated H8 | trace authority mean | trace innovation mean |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 205034050000 | 0 | 1.036437 | 0.987170 | 0.982417 | 0.986821 | 1.015216 | 0.084453 | 0.286629 |
| **205034050002** | **0** | 1.023488 | **1.000081** | 0.999426 | **1.000082** | **1.130430** | 0.045782 | 0.289755 |
| 205034050006 | 1 | 0.934212 | 0.755443 | 0.763232 | 0.755443 | 0.704488 | 0.890279 | 0.639015 |
| 205034050008 | 1 | 0.955733 | 0.901053 | 0.719565 | 0.901053 | 0.929521 | 0.928321 | 0.682108 |
| 205034050001 | 2 | 0.913680 | 0.466549 | 0.681035 | 0.466549 | 0.329466 | 0.940483 | 0.635713 |
| 205034050003 | 2 | 0.981523 | 0.436210 | 0.671765 | 0.436210 | 0.424523 | 0.972754 | 0.644035 |

The 320 failure is a separate, tiny mode-0 miss: H8 exceeds 1.0 by
`0.0000806700091314`. Authority is low, so this is not evidence of strong
authority overconfidence. It is consistent with a marginal predictor/null
boundary miss and is not the same severity as the repeated mode-1 pattern.

### Seed 340 / 0.3-R1

| ordinary seed | mode | H1 | H8 | H32 | event-H8 | ungated H8 | trace authority mean | trace innovation mean |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 305037050002 | 0 | 1.012296 | 0.995480 | 0.998783 | 0.995480 | 1.045304 | 0.053406 | 0.287269 |
| 305037050010 | 0 | 1.011537 | 0.991667 | 0.994691 | 0.991581 | 0.659279 | 0.116150 | 0.318937 |
| **305037050000** | **1** | 0.916896 | **1.038211** | 0.688344 | **1.038211** | **1.125379** | **0.970346** | **0.681296** |
| 305037050001 | 1 | 0.945735 | 0.960835 | 0.786607 | 0.960835 | 0.848380 | 0.854129 | 0.621428 |
| 305037050008 | 2 | 0.883776 | 0.573185 | 0.651259 | 0.573185 | 0.519608 | 0.947069 | 0.656079 |
| 305037050011 | 2 | 0.928462 | 0.352073 | 0.583078 | 0.352073 | 0.296634 | 0.974519 | 0.653759 |

The 340 failure is ordinary seed `305037050000`, mode 1. Its H8 failure is
`0.0382106730593255` above the gate. The learned H8 ratio is `1.125379`, and
trace authority is `0.970346`.

## Authority and innovation trajectories

Full serialized trajectories remain in the 0.2 and 0.3 artifacts (`2,988`
rows each). Relevant trajectory summaries are:

| run / episode | authority first 32 | authority last 32 | authority >= .99 | innovation first 32 | innovation last 32 |
|---|---:|---:|---:|---:|---:|
| 320 / failing mode-0 205034050002 | .141576 | .018746 | 0.000000 | .339613 | .264150 |
| 320 / passing mode-1 205034050006 | .651794 | .995767 | .640562 | .531984 | .677735 |
| 340 / failing mode-1 305037050000 | .797713 | .996397 | .861446 | .622552 | .693939 |
| 340 / passing mode-1 305037050001 | .982396 | .711191 | .620482 | .700780 | .515132 |

The 340 failing episode becomes more authoritative and saturates; the passing
mode-1 episode adapts downward as innovation falls. This supports an
allocation/calibration problem, not a slow-authority response. The 311
ordinary artifact stores H8-evaluation authority means but no ordinary
trajectory: the failing mode-1 episode has authority mean `.907365` and
innovation mean `.656448`; the passing mode-1 episode has `.872595` and
`.633751`.

## H8 rollout and event diagnostics

The recorded H8 rollout vectors were re-evaluated against deterministic target
episodes. The rehydrated ratios reproduce the artifact values to approximately
`1e-8`:

| run / episode | actual H8 / null H8 | event-H8 / null event-H8 | event-bearing trace rows |
|---|---:|---:|---:|
| 320 / failing mode-0 205034050002 | 1.000080674 | 1.000081943 | 484 / 498 |
| 340 / failing mode-1 305037050000 | 1.038210652 | 1.038210652 | 498 / 498 |

Both mode-1 0.1/0.3 failures have H8 and event-H8 equal in the stored
scientific results. The 320 event-only difference is negligible. Event
handling is therefore not a sufficient explanation.

Rollout-vector clipping is low in the failing 340 mode-1 episode: mean
absolute clipping at H8 is about `1.14%`, compared with about `0.87%` in its
passing mode-1 counterpart. There is no NaN/Inf, explosive magnitude, or
general numerical blow-up. The defect is horizon-specific error against the
target, not an unbounded numerical state.

## Recorded-episode counterfactuals

For 0.2/0.3 one-step trace rows, the implementation satisfies approximately:

```text
gated_error = (1 - authority) * null_error
               + authority * ungated_learned_error
```

The following are engineering diagnostics only:

- `null only` and `authority clamped to zero`: recorded null error;
- `learned only`: recorded ungated learned error;
- `frozen authority`: episode mean authority applied to every row;
- `authority delayed`: one-row lag, initialized at zero;
- `oracle mixing`: row-wise minimum of null and learned error.

| episode | null only | learned only | actual | frozen authority | delayed authority | oracle row minimum |
|---|---:|---:|---:|---:|---:|---:|
| 320 failing mode-0 205034050002 | .288153 | .431974 | .294855 | .294737 | .294740 | .286751 |
| 340 failing mode-1 305037050000 | .680388 | .641818 | .642539 | .642962 | .643077 | .618434 |
| 340 passing mode-1 305037050001 | .619478 | .587068 | .589654 | .591796 | .589994 | .556356 |

The 340 failing episode is better than null at one step but fails at H8. That
separates the local authority path from the H8 rollout path. The 320 failure
has learned-only error substantially worse than null, but low authority limits
the damage; its H8 miss is correspondingly tiny. The 311 ordinary trace lacks
the fields needed for these counterfactuals, so no unsupported replay was
claimed.

## Hypothesis classification

| hypothesis | verdict | evidence |
|---|---|---|
| A. learned predictor is bad in mode 1 | **SUPPORTED** | Both 311 and 340 failing episodes have ungated H8 ratios above 1.0: `1.013993` and `1.125379`. Passing mode-1 episodes are below 1.0. |
| B. authority gives learned predictor too much control | **SUPPORTED as proximate cause** | Failing mode-1 authority is high (`.907365` and `.970346`) while learned H8 is worse than null. Zero-authority/null-only would avoid the observed mixture failure. |
| C. authority reacts too slowly | **NOT SUPPORTED** | The 340 failure is highly authoritative and saturating, not persistently low or delayed. |
| D. H8 rollout itself is unstable | **PLAUSIBLE, H8-localized** | 340 has better one-step gated error than null but worse H8 error; 311 also passes H1/H32 while failing H8. No general numerical explosion is present. |
| E. event handling causes the failure | **NOT SUPPORTED** | Event-H8 equals H8 in both mode-1 failures; the 320 event-only difference is negligible. |
| F. evaluator/metric artifact | **REFUTED for 0.2/0.3 H8 ratios** | Deterministic target rehydration reproduces serialized H8 ratios to approximately `1e-8`. |
| G. ordinary seed variance | **POSSIBLE CONTRIBUTOR, INSUFFICIENT ALONE** | Four other mode-1 episodes pass, but the two failures share mode, horizon, high authority, and nearly identical H8 ratio. |
| H. combination | **BEST CURRENT EXPLANATION** | Mode-1 learned H8 weakness plus high authority, expressed through an H8-specific rollout interaction. |

## Answers to the decision questions

1. **Is the mode-1 H8 failure repeated evidence of a mechanism defect?**
   Yes, at the level of a repeated vulnerability in the predictor/authority
   path. It is not yet evidence that every mode-1 seed fails.

2. **Is the defect in the predictor or authority allocation?** Both are
   implicated. The learned H8 predictor is worse than null in both failures,
   and authority is high enough to expose that weakness. The precise division
   between model calibration and authority policy remains unresolved.

3. **Can it be localized without changing the epistemic subsystem?** Yes.
   The failure appears before belief maintenance, in H8 prediction/authority
   allocation. Metric A, Metric B, safety, provenance, and scaling remain
   unchanged and passing in 340-R1.

4. **Should seed 341 run unchanged?** No. The repeated mode-1 pattern crosses
   the stated decision threshold for stopping 0.3 predictive seeds.

5. **Should a predictive-authority successor be created?** Yes. Create a
   separate predictive-authority successor with the epistemic/provenance
   subsystem carried forward unchanged. Do not alter 0.3 or spend seed 341 in
   the current design.

## Criteria and classification

```text
predictive authority:              FAIL
mode-1 failure repetition:         PASS as a localized warning signal
predictor/authority localization:  PASS
epistemic coupling:                NOT OBSERVED
event-handling explanation:        FAIL / unsupported
metric-artifact explanation:      FAIL / refuted for 0.2/0.3
ordinary-variance-only explanation: FAIL / insufficient
counterfactual H8 attribution:    INSUFFICIENT (learned H8 rollout absent)
```

## Assumption register

- **Verified:** 311, 320-R3, and 340-R1 artifacts are present and readable;
  340-R1 has a valid receipt and all frozen source hashes.
- **Verified:** no new scientific seed was run for this autopsy; 0.3 source
  and scientific artifacts were not modified.
- **Verified:** the 340 epistemic result remains Metric A `132/132`, Metric B
  `4571/4571`, zero false durable claims, perfect rollback, and deterministic
  replay.
- **Verified:** 0.2/0.3 H8 actual/null ratios reproduce from serialized rollout
  vectors and deterministic target rehydration.
- **Checkable but unavailable:** ordinary per-step authority, innovation, and
  event traces for 311. The diagnostic replay contains developmental-challenge
  traces, not ordinary-test traces.
- **Checkable but unavailable:** independent learned-only and frozen-authority
  H8 rollouts. The artifacts serialize only the final gated H8 rollout, not
  the learned-only intermediate rollout at each step.
- **Unfalsifiable here:** whether this toy-world predictor defect transfers to
  long-lived real-world agents.

## Credit assignment

The evidence assigns no causal credit or blame to the provenance store. The
scientific 340 artifact shows the epistemic subsystem passing while predictive
H8 fails. Within the predictive path, the learned H8 error is already above
null in both repeated failures; high authority then mixes that weak rollout
into the final prediction. The remaining attribution between model
representation, authority calibration, and H8 recurrence is entangled.

## Verification gap

The current artifacts do not support a learned-only H8 rollout replay, a
counterfactual authority policy evaluated through the full H8 recurrence, or a
complete ordinary-test per-step trace for 311. Those gaps prevent choosing
between a pure model defect and a pure authority-policy defect.

## Stop / continue

**STOP.** Do not run seeds 341, 342, 350, or 351. Do not modify the 0.3
epistemic/provenance subsystem. The next bounded work item is design-only:
specify a separate predictive-authority successor whose diagnostics expose
learned-only H8 rollouts and authority counterfactuals before authorizing any
fresh scientific seed.

## Maturity status

The predictive-authority claim is defined, serialized, tested, replayed, and
falsified at the current H8 threshold. It is not yet mature: causal attribution
between predictor and authority remains incomplete, and real-world transfer is
untested. The epistemic/provenance claim is substantially more mature, but its
success does not qualify the complete architecture while predictive authority
fails.

## Artifact checksums

```text
0.1 development_seed311.json
b51de9e7e7221c23226f95507fea446444645fc9279d5e99398049c81e78c58

0.1 seed311_autopsy_trace.json
675fac0bda38a928af1c65de42186d2853295929ba5a08dbf9520ecc750dcf91

0.2 development_seed320.json
db51486f9e72b11bb2f4f6ec97642f4e0c6c15c61bc88f48fff345d81d13fe9b

0.3 development_seed340.json
b62e89e515d741235d3d6bb4433f654af0fed6ef98aa56810c48e7253c1c84be
```

No GitHub activity occurred. No new scientific seed was executed.
