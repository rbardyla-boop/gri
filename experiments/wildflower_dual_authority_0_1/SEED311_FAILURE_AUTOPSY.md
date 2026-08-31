# Seed 311 failure autopsy

This is a local-only post-result analysis. It does not replace or modify the
scientific result artifact, and no seed 312+ was run.

## Bottom line

Seed 311 is a predictive-gate **FAIL**, but the H8 failure is localized to one
ordinary-test episode. The apparent 402 Metric-B failures are not 402 claims
left unrecomputed: the diagnostic trace shows all 2,708 Metric-B opportunities
were revoked after witnessing and committed again after recomputation. The
402 failures are parity claims whose upstream support lineage changed while
their immediate parent claim keys remained equal. The frozen predicate requires
the immediate parent tuple to change, so it misclassifies transitive
recomputation as failure.

The result is therefore:

```text
predictive mechanism:    FAIL
epistemic preservation:  PASS, 1784/1784
epistemic recomputation: FAIL under the frozen metric; semantic recovery 2708/2708
safety:                   PASS
control superiority:     INSUFFICIENT
scaling:                 PASS for the completed workload
deterministic replay:    PASS for the recorded ledger checks
seed 312:                DO NOT START
```

## Evidence and integrity

Audited files:

- [`development_seed311.json`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/artifacts/development_seed311.json>) — frozen scored result;
- [`seed311_autopsy_trace.json`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/artifacts/seed311_autopsy_trace.json>) — separate diagnostic replay trace;
- [`seed311_diagnostic_replay.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/seed311_diagnostic_replay.py>) — trace harness;
- [`metrics.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/metrics.py>) — metric definitions;
- [`run_dual_authority01.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/run_dual_authority01.py>) — scorer and controls;
- [`store.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/store.py>) — incremental store;
- [`test_seed311_failure_autopsy.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/tests/test_seed311_failure_autopsy.py>) — new deterministic regression tests.

The frozen result was checked before and after the diagnostic replay:

```text
development_seed311.json
SHA-256: b51de9e7e7221c23226f95507fea4464446445fc9279d5e99398049c81e78c58
```

The original artifact's semantic receipt remains:

```text
971852b2ae87a5a2985a3d4c499ac9b05f3b1ea6941dc856ab070929dd136582
```

The artifact contains no raw transition stream, support IDs, per-transition
latency, burn-in authority, or event counts. Because those fields were absent,
the permitted seed-311 diagnostic replay captured them into a new file without
calling the scorer's `main` and without writing the frozen JSON. The replay
receipt itself is not expected to equal the original receipt: the receipt
includes runtime and scaling wall-clock fields. The diagnostic trace's
transition, recomputation, and duplicate aggregates match the corresponding
stored values.

Validation completed:

```text
python -m compileall -q experiments/wildflower_dual_authority_0_1    PASS
ruff check experiments/wildflower_dual_authority_0_1                  PASS
PYTHONHASHSEED=0 python -m pytest -q -W error experiments/.../tests    PASS, 39 tests
qualification guard for 314 and 315                               PASS
frozen artifact byte/hash preservation                              PASS
```

## 1. Predictive H8 autopsy

The artifact serializes `h8.model` from `eval_authority`, so that column is
the authority-controlled error. It serializes only the ungated learned/model
error ratio. The learned absolute error below is reconstructed as
`ungated_h8_ratio * h8.baseline`; it was not serialized directly.

`authority_mean` is the rollout/evaluation mean. Authority at burn-in is not
stored. Surprise-event counts are not stored; `event_h8` is available only as
an aggregate error ratio.

| evaluator mode | episode seed | H1 ratio | H8 ratio | H32 ratio | event H8 | H8 authority mean | null H8 error | learned H8 error* | controlled H8 error |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1931950004 | 1.017332 | 0.996322 | 0.999437 | 0.996249 | 0.078165 | 2.431217 | 2.490906 | 2.422275 |
| 0 | 1931950006 | 1.023255 | 0.994483 | 0.994322 | 0.994147 | 0.091114 | 2.515873 | 2.526778 | 2.501992 |
| 1 | 1931950001 | 0.989970 | 0.800034 | 0.764738 | 0.800034 | 0.872595 | 3.486772 | 2.352746 | 2.789538 |
| 1 | **1931950002** | 0.906429 | **1.038178** | 0.772412 | **1.038178** | 0.907365 | 2.402116 | 2.435729 | 2.493825 |
| 2 | 1931950000 | 0.843414 | 0.781593 | 0.651891 | 0.781593 | 0.990803 | 3.753968 | 3.107754 | 2.934074 |
| 2 | 1931950005 | 1.041738 | 0.938284 | 0.678877 | 0.938284 | 0.982798 | 2.973545 | 2.921049 | 2.790031 |

The H8 gate failure is concentrated in mode 1, episode `1931950002`. In that
episode the learned error and controlled error are both worse than the null
baseline, despite high authority (`0.907365`). This is evidence of a
predictive-model/authority calibration failure in that episode, not evidence
that epistemic rollback suppressed a useful prediction.

Aggregate predictive gates:

```text
h1 non-inferior all:  PASS
h8 better all:       FAIL, max 1.038178
h8 mean 10%:         FAIL, mean 0.924816
h32 better all:      PASS
h32 mean 15%:        PASS
event-h8 mean 10%:   FAIL, mean 0.924748
```

## 2. Exact Metric-B opportunity breakdown

The diagnostic replay captured 5,145 derived transitions: 1,715 in each of
the three challenge episodes. The 2,708 Metric-B opportunities break down as:

| episode | evaluator mode | evaluator seed | derived transitions | opportunities | successes | failures |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 2932000003 | 1,715 | 775 | 626 | 149 |
| 1 | 1 | 2932000001 | 1,715 | 907 | 799 | 108 |
| 2 | 2 | 2932000000 | 1,715 | 1,026 | 881 | 145 |
| **total** | — | — | **5,145** | **2,708** | **2,306** | **402** |

Every one of the 2,708 opportunities had this state sequence:

```text
before witness:  provisional
after witness:   revoked
after recompute: committed
```

All 402 failures are `REL_ORDER_PARITY` claims. There were no failures for
`REL_LEFT_OF` or `REL_ABOVE`.

Representative failed rows:

| episode/tick | claim | original support | invalidated lineage | new support | after witness | after recompute |
|---|---|---:|---|---:|---|---|
| 0 / 17 | `(3000000018, 1)` | 65 | 53–61 | 78 | revoked | committed |
| 1 / 15 | `(3010000016, 0)` | 13 | 1–9 | 26 | revoked | committed |
| 2 / 18 | `(3020000019, 1)` | 91 | 79–90 | 104 | revoked | committed |

For each example, the new support is effective and the claim has a committed
state after recomputation. The original support also becomes effective again.
The original and new parity supports have the same direct parent claim tuple;
the changed information is below that level, in the support lineage of the
relation-parent claims. No direct descendant remained in the closed transition
region for these parity roots.

The exact cause is visible in the frozen implementation:

1. `materialize_prediction` proposes coordinate claims, derives pair relations,
   then derives parity from the six relation claim keys.
2. `materialize_world_witness` adds world coordinate supports and disables
   non-world supports for those slots.
3. Store propagation invalidates relation and parity supports through reverse
   dependency edges.
4. `derive_from_committed_coordinates` creates new relation supports from the
   witnessed coordinate claim keys, then creates a new parity support from the
   same six relation claim keys.
5. The classifier marks a parent change when an immediate parent claim is not
   committed after the witness, but declares success only when the new support's
   immediate `parents` tuple differs from the original tuple.

The relevant predicates are in [`metrics.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/metrics.py:200>):
`parent_keys_changed` examines parent claim status, while
`recomputation_success` compares only the direct parent tuple. That is a
transitive bookkeeping/representation defect in the metric boundary, not a
demonstrated failure to restore the claim's semantic status.

## 3. Precision: exact TP/FP and support counts

The trace found at most one reconstructed support ID per transition. The exact
boolean denominator is therefore 4,529 transitions, with 2,306 true positives
and 2,223 false positives under the frozen predicate.

| episode | reconstructed transitions | TP / frozen successes | FP under frozen predicate | exact precision | Metric-B opportunities | B failures |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1,579 | 626 | 953 | 0.396453 | 775 | 149 |
| 1 | 1,435 | 799 | 636 | 0.556794 | 907 | 108 |
| 2 | 1,515 | 881 | 634 | 0.581518 | 1,026 | 145 |
| **global** | **4,529** | **2,306** | **2,223** | **0.509163** | **2,708** | **402** |

The stored `recomputation_precision = 0.511589` is the unweighted arithmetic
mean of the three episode precisions, not the global TP/(TP+FP) value. This is
an evaluator/accounting weakness. It does not change the underlying exact
counts.

The 402 Metric-B false positives are the parity subset of the 2,223 exact
recompute duplicates. The other duplicate recomputations are mostly correct
pair-relation supports whose direct parent keys did not qualify as changed.

## 4. Duplicate-support audit

An exact duplicate is the same packet, support kind, and parent tuple inserted
again. The replay captured all three insertion phases and excluded the later
scaling probe.

| episode | prediction inserts | witness inserts | recompute inserts | total inserts | unique signatures | exact duplicates | duplicate rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 3,185 | 1,470 | 1,715 | 6,370 | 5,417 | 953 | 0.149608 |
| 1 | 3,185 | 1,470 | 1,715 | 6,370 | 5,734 | 636 | 0.099843 |
| 2 | 3,185 | 1,470 | 1,715 | 6,370 | 5,736 | 634 | 0.099529 |
| **total** | **9,555** | **4,410** | **5,145** | **19,110** | **16,887** | **2,223** | — |

All 2,223 exact duplicates were inserted in the recomputation phase, with the
matching first signature created in the prediction phase. No witness-phase
duplicates were found. This is not hidden multiple-support inflation inside a
single transition: the trace observed one reconstructed support ID per
transition. It is repeated support creation across prediction and recompute.

The appropriate repair is to make support identity explicit: either canonicalize
exact signatures when duplicate supports are semantically interchangeable, or
retain separate IDs but record a lineage/provenance fingerprint for the
effective parent supports. A raw direct-parent-tuple comparison is insufficient
for transitive claims such as parity.

## 5. Recompute latency

The artifact has no monotonic timestamps or per-transition timing records, so
wall-clock latency distributions cannot be recovered. The diagnostic trace
does establish the logical latency:

```text
Metric-B opportunities reaching revoked state after witness: 2,708 / 2,708
reaching committed state after the same tick's recompute:   2,708 / 2,708
logical tick delay:                                          0
recompute phase delay:                                       one witness→recompute stage
```

The 402 metric failures are therefore not hidden temporary losses that stayed
unrepaired. A future preregistration should record event sequence number and
monotonic time separately, and should report temporary revoked duration rather
than inferring latency from final state.

## 6. Controls and independent-control limitation

The artifact reports these seven names, but the scorer does not instantiate
seven independent stores on the same recorded transition stream. The helper in
[`run_dual_authority01.py`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/run_dual_authority01.py:253>) derives several rows directly from the same `packet_rows` and uses fixed control assumptions for some rows.

| control | false durable claims | false rate | durable coverage | stale descendants | Metric A | Metric B |
|---|---:|---:|---:|---:|---|---|
| DUAL_AUTHORITY | 0 | 0.000000 | 0.930926 | 0 | 1784/1784 | 2306/2708 |
| DIRECT_COMMIT | 2,171 | 0.227211 | 0.772789 | not collected | not collected | not collected |
| CONFIDENCE_COMMIT | 1,577 | 0.165044 | 0.478493 | not collected | not collected | not collected |
| DAG_NO_WITNESS | 0 | 0.000000 | 0.000000 | not collected | not collected | not collected |
| WITNESS_NO_DAG | 616 | 0.064469 | 0.000000 | 616 | not collected | not collected |
| WITNESS_PLUS_RECOMPUTE_NO_DAG | 0 | 0.000000 | 1.000000 | not collected | not collected | not collected |
| DAG_PLUS_WITNESS_NO_RECOMPUTE | 0 | 0.000000 | 0.489377 | not collected | not collected | not collected |

Rollback counts, preservation counts, and recomputation counts for the other
six control summaries were not collected. The zero/full-coverage
`WITNESS_PLUS_RECOMPUTE_NO_DAG` row is not an independent recompute-everything
execution; it is a control summary emitted by the evaluator helper. Therefore
control superiority is **INSUFFICIENT**, not PASS.

## 7. Hostile interpretations

1. **Witness alone explains everything — rejected.** `WITNESS_NO_DAG` leaves
   616 stale descendants and false durable claims.
2. **Recompute-everything explains everything — unresolved.** The reported
   no-DAG recompute row has zero false claims and full coverage, but it is not an
   independent store run and carries no provenance.
3. **DAG alone explains everything — rejected.** `DAG_NO_WITNESS` has no durable
   coverage.
4. **Metric-A denominator is tiny — rejected.** It is 1,784.
5. **Metric-B denominator is tiny — rejected.** It is 2,708 opportunities and
   4,529 reconstructed-support transitions for precision.
6. **Duplicate support creation inflates success — confirmed as a mechanism
   concern, not as an explanation for the whole result.** There are 2,223
   exact prediction→recompute duplicates; the trace did not find multiple
   reconstructed IDs per transition.
7. **Aggressive revocation makes safety look good — partly unresolved.** The
   trace confirms a temporary revoked interval for every Metric-B opportunity,
   but the final safety metrics are zero false durable claims and zero stale
   support survival with 93.09% coverage.
8. **Regeneration latency hides knowledge loss — rejected for Metric A.** Metric
   A is evaluated after witness and before recompute; latency timing itself is
   not serialized.
9. **Bounded storage favors one mechanism — not supported in this run.** The
   challenge maximum was 19 claims against an 8,192 bound.
10. **Instrumentation changes state or timing — timing changed, semantic state
    did not show a divergence.** The trace harness uses read-only snapshots and
    its aggregate counts reproduce the stored A/B/duplicate totals. Its receipt
    cannot be compared byte-for-byte because scaling wall time is hashed.

## Smallest reproducing case and repair

The new test creates two committed parent claims, a derived parity-like child,
and replacement world supports for the same parent claim keys. The child is
revoked after witness, becomes committed after recompute, and receives a new
support with the same direct parent tuple. The frozen classifier reports
`recomputation_success == false`. This reproduces the exact seed-311 failure
class without changing seed 311.

Minimal repair for a future preregistered version:

1. Keep direct claim keys for alternate-support semantics.
2. Track effective parent-support lineage (or a canonical support fingerprint)
   alongside each derived support.
3. Define recomputation success from a new effective grounded support plus final
   commitment, and require a lineage change rather than a direct parent-key
   change.
4. Report weighted global TP/FP counts alongside per-episode rates.
5. Report exact duplicate counts and provenance phase separately from Metric-B
   precision.
6. Re-run fresh, unspent development seeds only after this repair is frozen and
   reviewed. Seed 312 remains unauthorized for this turn.

No frozen experiment file was altered, and execution stops here.
