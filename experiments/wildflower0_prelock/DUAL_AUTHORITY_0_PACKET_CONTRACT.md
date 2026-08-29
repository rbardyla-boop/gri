# WILDFLOWER Dual-Authority-0 machine-native packet contract

Status: **FROZEN FOR DUAL-AUTHORITY-0 PREFLIGHT**

This contract fixes the interchange shape used by Dual-Authority-0. It is an implementation boundary, not a claim that this packet is a universal or final machine language.

## Runtime rule

The cognitive path receives and emits integer packets only.

Exactly six fields, in order:

| Index | Field | Runtime type | Role |
|---:|---|---|---|
| 0 | `STABLE_REFERENCE` | unsigned integer | stable slot identity |
| 1 | `ACT` | unsigned integer | machine operation code |
| 2 | `SUBJECT` | unsigned integer | machine entity reference |
| 3 | `RELATION` | unsigned integer | machine relation code |
| 4 | `OBJECT` | unsigned integer | machine entity/reference argument |
| 5 | `VALUE` | signed integer | scalar machine value |

No string, token, text label, transcript, or language embedding is a legal packet field.

Human-readable constant names exist only in source/documentation.

## ACT codes

```text
1 = proposal from predictive path
2 = direct world observation
3 = derived claim
```

## Relation codes used in this experiment

```text
1 = x-coordinate cell
2 = y-coordinate cell
3 = pairwise x ordering
4 = pairwise y ordering
5 = second-generation ordering parity
```

These numeric relations are deliberately small and fixed. Dual-Authority-0 does not score representation discovery.

## Stable-reference rule

`STABLE_REFERENCE` names a time-scoped claim slot, not a truth value.

A prediction and a later world observation about the same slot therefore share the same stable reference even when their `VALUE` differs. This permits explicit contradiction without string matching.

Coordinate, pair-relation, and second-generation relation slots occupy separate integer namespaces.

## Epistemic metadata is not smuggled into the packet

Claim status and justification structure are maintained by the epistemic store, not hidden in extra packet fields.

The store may track:

- provisional / committed / revoked / conflicted state;
- support kind;
- parent claim references;
- active/effective support;
- append-only transition receipts.

Those structures are numeric machine state. They do not expand the six-field packet.

## Direct witness boundary

Only directly sensor-derived coordinate packets may enter with `ACT=2` as independent world witnesses in Dual-Authority-0.

Pair relations and parity are **not** injected as witness answers. They must be derived again from committed coordinate parents.

Evaluator-side relation/parity truth may be constructed for scoring, but it may not be passed to the cognitive store.

## Durability rule

A packet-derived claim is durable only when at least one active support path is rooted in an `ACT=2` world observation.

Therefore:

- proposal alone → provisional;
- derivation from provisional parents → provisional;
- matching world observation → parent claim committed;
- derivation whose parent claims are committed → committed;
- contradiction → incompatible proposal support retired;
- descendant with no surviving parent support → revoked;
- descendant with alternate surviving support → preserved.

Predictive-authority magnitude is not a durability credential.

## Encoding used for exact replay

For individual/small packets:

- `STABLE_REFERENCE`, `ACT`, `SUBJECT`, `RELATION`, `OBJECT` use unsigned varints;
- `VALUE` uses ZigZag + unsigned varint;
- stable reference remains in-band.

`encode_packet()` and `decode_packet()` must roundtrip byte-exactly.

Batch encoding is not part of the scientific variable. If later engineering needs batching, the historical ENCODING lineage suggests columnar batching can become cheaper as batch size grows, but the exact threshold is workload dependent and is not imported as a universal rule.

## Why this conservative choice was selected

Historical ENCODING results, recovered without rerunning archived experiments, support only a narrow engineering prior:

- on the original tiny ENCODING-0 corpus, in-band stable identity + shared indexes + varints was the byte leader;
- external handle variants did not win the frozen ENCODING-1 envelope;
- batching became preferable in larger repeated traffic;
- a held-out generator preserved the direction of the batching effect but moved exact crossover thresholds;
- a workflow-shaped 1,536-transformation trace reproduced the predicted varint-to-batch direction.

Dual-Authority-0 therefore uses the simplest already-supported small-packet shape and refuses to turn encoding choice into another degree of freedom.

## Out of scope

This contract does not establish:

- universal optimality;
- production-network efficiency;
- online dictionary growth behavior;
- distributed dictionary synchronization;
- loss recovery;
- arbitrary representation invention;
- natural language understanding.

Any future change to the six semantic fields is a new representation experiment and cannot be smuggled into a Dual-Authority-0 repair.
