# Dual-Authority-0.2 provenance contract

This document defines the representation and event semantics for the local
successor to the frozen 0.1 experiment. It is an implementation contract, not
a scientific result.

## Two identities on every derived support

A derived support contains:

```text
packet
semantic_parent_claim_keys
parent_lineage_fingerprint
```

`semantic_parent_claim_keys` answers “what claims does this derivation
depend on?” A claim key is `(stable_reference, value)` and is not replaced by a
support ID.

`parent_lineage_fingerprint` answers “which effective grounded support paths
justified those parent claims when this support was created?” It is a SHA-256
digest of canonical machine-native data. It is never derived from Python
object identity, insertion order, or natural-language text.

The effective grounded lineage for a claim is the sorted set of path digests
for enabled, effective, grounded supports. A derived support is grounded only
when:

1. all semantic parents are grounded; and
2. its stored parent-lineage fingerprint equals the parents’ current
   canonical lineage fingerprint.

Therefore a support can retain the same packet and the same semantic parent
keys while becoming ungrounded when the evidence lineage changes. The repair
then creates a new support with the changed fingerprint.

Canonical input uses numeric tuples, sorted path digests, sorted semantic
parent keys, and JSON-style canonical encoding before SHA-256. The append-only
numeric ledger records the fingerprint as an integer and has a replay check.

## Four non-equivalent events

### Continuous preservation

The original derived support has an invalidated lineage, but a different
support for the same claim was already grounded before the witness and remains
grounded after it. The claim must remain committed continuously.

### True recomputation

The original support was grounded before the witness and is no longer grounded
after it. Corrected grounded evidence is available in the recomputation
snapshot. A successful recomputation creates a newly effective grounded
support, commits the claim, and changes the lineage fingerprint.

### Semantic duplicate

The packet, semantic parent keys, and lineage fingerprint are identical. The
canonical support ID is reused; a separate event-history occurrence records
the reconsideration. The active DAG does not grow.

### Same semantics / new provenance

The packet and semantic parent keys are identical, but the lineage fingerprint
differs. This is a new epistemic support identity, not a duplicate. The 402
REL_ORDER_PARITY cases identified in seed 311 are this event class.

## Metric A: alternate-support preservation

The unit is an original derived support. An opportunity requires:

- its packet value was correct before the witness;
- an original grounded support in its lineage is no longer grounded after the
  witness;
- a different support for the same claim was grounded before and remains
  grounded after the witness.

Success requires the claim to be committed in the after-witness snapshot.
Report opportunity and success counts and `successes / opportunities`.

## Metric B: recomputation after parent change

The unit is an original derived support. An opportunity requires:

- its packet value was correct before the witness;
- its original grounded lineage becomes invalid;
- the original support is no longer grounded after the witness; and
- corrected grounded evidence is available in the recomputation snapshot.

Success requires a newly effective grounded derived support for the claim,
final commitment, and a lineage fingerprint different from the invalidated
support. Immediate semantic parent keys may be unchanged.

Global precision is `true-positive reconstructed transitions /
(true-positive + false-positive reconstructed transitions)`. Global recall is
`true-positive reconstructed transitions / opportunities`. Episode-level
counts and ratios are reported separately. An unweighted mean of episode rates
is never substituted for the global ratio.

## Canonicalization and history

The store measures support insertion attempts, canonical creations, canonical
reuses, provenance changes, semantic duplicate reuses, active support count,
and historical event count. Repeated identical derivations reuse one active
support ID while preserving event occurrences in append-only history.

## Safety invariants

The store must preserve acyclicity, reject missing parents and cycles without
mutation, honor the active-claim bound, reject non-finite/non-integer packet
fields, and make replay produce the same ledger head. Incremental propagation
must match the reference semantic oracle after every mutation in the hostile
tests.
