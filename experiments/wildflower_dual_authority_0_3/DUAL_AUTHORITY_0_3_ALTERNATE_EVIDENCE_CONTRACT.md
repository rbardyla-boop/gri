# Dual-Authority-0.3 alternate-evidence contract

## Purpose

The prior 0.2 scientific stream tested removal and recomputation but did not
present two grounded, independently justified support paths before a witness.
This contract supplies that missing falsifiable workload. It tests whether a
correction removes only the unsupported lineage while preserving a target
whose other justification was already valid.

The mechanism sees only `RecordedTransition.mechanism_frame`: numeric
predictions, numeric witnesses, numeric recomputations, and authority. Truth,
opportunity labels, expected case outcomes, and path accounting are
evaluator-only sidecars.

## Machine-native independence

For a grounded world support, define:

```text
root_identity = SHA256(("world-root", complete_numeric_world_packet))
```

For a derived support, enumerate the Cartesian product of grounded root sets
of its semantic parent claims and union the roots in each product element.
The resulting path identity is:

```text
path_identity = SHA256(("grounded-root-path", sorted(root_identities)))
```

Two paths are independent exactly when their root-identity sets are disjoint.
The evaluator computes the maximum number of pairwise-disjoint grounded root
sets before the witness. This rejects support-ID uniqueness, same-key claims,
different labels, prose descriptions, and object identity as proxies for
independence. A cryptographic identity collision is treated conservatively as
the same lineage rather than as independent evidence.

## Exact Metric A

An opportunity is counted only for a target that is correct and committed
before the witness, has at least two grounded paths, has at least two
independent root lineages, and loses at least one path while retaining at
least one pre-existing independent path immediately after the witness.

The success predicate is:

```text
target remained continuously COMMITTED
and invalidated path is no longer grounded
and surviving pre-existing independent path is grounded
and no new post-witness path was needed
```

The denominator excludes a duplicate lineage, a shared invalidated root, an
alternate that was already ungrounded, an alternate made only after the
witness, and a revoked-then-recomputed target. Metric A and Metric B are
mutually exclusive for a target event: a post-witness reconstruction is a
Metric-B event, not preservation.

## Guaranteed workload

The generator creates 40 valid positive events per challenge episode. Hostile
case 1 is intentionally represented by that guaranteed-positive construction,
not emitted as a duplicate event. The emitted workload is therefore 40
guaranteed-positive events plus 17 additional hostile events (codes 2--18).
All 18 hostile behaviors are still covered. Each episode emits exactly 57
events and has 44 expected Metric-A opportunities; three episodes emit 171
events and have 132 expected opportunities. The hostile suite is deterministic
and includes these 18 case codes:

| Code | Case | Intended evaluator behavior |
| ---: | --- | --- |
| 1 | true independent alternate | `PRESERVED`, Metric A opportunity |
| 2 | both paths invalidated | `REVOKED`, no A |
| 3 | same-root masquerade | `UNCHANGED`, no A |
| 4 | duplicate lineage | `REVOKED`, no A |
| 5 | alternate already ungrounded | `REVOKED`, no A |
| 6 | alternate only after witness | `RECOMPUTED`, Metric B diagnostic |
| 7 | semantic value changes | `REVOKED`, no A |
| 8 | one of three survives | `PRESERVED`, Metric A opportunity |
| 9 | two of three survive | `PRESERVED`, Metric A opportunity |
| 10 | nested transitive alternate | `PRESERVED`, Metric A opportunity |
| 11 | diamond shared ancestor | `REVOKED`, no A |
| 12 | five-level derivation | `PRESERVED`, Metric A opportunity |
| 13 | alternate disappears and returns | `RECOMPUTED`, Metric B diagnostic |
| 14 | canonical reuse, no independence | `REVOKED`, no A |
| 15 | lineage-collision rejection | `UNCHANGED`, no A |
| 16 | same parent keys, changed lineage | `REVOKED`, no A |
| 17 | partial ancestor overlap | `UNCHANGED`, no A |
| 18 | unrelated branch | `UNCHANGED`, no A |

Cases 1, 8, 9, 10, and 12 are positive pre-existing-alternate cases. Case 1
is represented by every one of the 40 guaranteed events; cases 8, 9, 10, and
12 are emitted once as additional hostile cases. Thus the deterministic
engineering result is 57 events, 44 Metric-A opportunities, and 44 successes
per episode. The suite intentionally includes both positive and negative
cases so the denominator cannot be manufactured by counting every target
with multiple support records.

## Serialized event schema

Every challenged target records at least:

```text
event_id
claim_key
pre_witness_grounded_path_count
pre_witness_independent_root_count
invalidated_path_ids
surviving_preexisting_path_ids
post_witness_status
recomputation_attempted
new_post_witness_path_ids
primary_classification
metric_a_opportunity
metric_a_success
expected_metric_a_opportunity
false_opportunity_classification
metric_b_opportunity
metric_b_success
```

Path IDs are canonical hashes, not support IDs. The event stream is
evaluator output and never enters model, store, or control decisions.

## Failure interpretation

If positive opportunities fail while the hostile cases classify correctly,
the result is a mechanism-selectivity failure. If counts or labels disagree
with the constructed graph, it is an evaluator/accounting or graph
bookkeeping failure. If same-key changed-lineage cases collapse, it is a
representation or canonicalization failure. If all positive cases are
classified as no-opportunity, it is a challenge-construction failure and no
scientific conclusion is permitted.

## Non-authorizations

This contract does not authorize a scientific seed, thresholds, tuning,
qualification, GitHub activity, or modification of 0.2 files/artifacts.
