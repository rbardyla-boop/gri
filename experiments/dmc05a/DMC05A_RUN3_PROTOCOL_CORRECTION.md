# DMC-05A Run 3 protocol correction

Run 2 completed mechanically but its emitted
`DMC_05A_BOUNDED_MEMORY_ADVANTAGE` label is scientifically invalid. The
preserved audit is `artifacts/dmc05a/DMC05A_RUN2_PROTOCOL_AUDIT.json`, and the
unaltered Run 2 evidence is under
`artifacts/dmc05a/run2_protocol_invalid/`.

This correction is required by the original user-level DMC-05A instruction:
the exact structured store must exploit the existing entity/field/update
structure like a competent conventional implementation and must not be
crippled to make DMC win.

## Run 2 defects

1. `exact_structured` and `conventional_retrieval` indexed only the 64-way A/B
   address. They ignored active mission scope, salience, entity, field, and
   supersession even though those fields are explicit benchmark input and are
   the only utility information supplied to DMC retention. At large loads,
   irrelevant writes reused A/B addresses and were incorrectly treated as
   valid temporal versions.
2. The bounded-advantage verdict checked only exact structured memory and
   conventional retrieval. It ignored `recent_window_16`, which matched DMC
   capability at every load with 16 persistent and 16 working records.
3. Exact structured critical recall was measured against all persistent index
   buckets instead of its bounded retrieved bucket.

Run 2 is therefore classified as `DMC_05A_ACCOUNTING_INVALID`; its machine
label is retained only as failure evidence.

## Corrected conventional policy

The strong conventional systems may compute a transparent utility predicate
from exactly these existing fields:

```text
retention_metadata.family
retention_metadata.entity
retention_metadata.field
retention_metadata.creation_episode
retention_metadata.salience
retention_metadata.supersedes
metadata.scope_events / active mission scope
```

For mission-set, supersession, and utility-change records, an index entry is
utility-eligible when its entity belongs to the final active mission scope.
For salience and distractor-flood records, it is eligible when salience is
`HIGH`. This is the deterministic, zero-training counterpart of the two
authorized DMC retention features `[mission_membership, high_salience]`.

No relevance decision may inspect a target record ID, answer, value, oracle
view, query identity, case ID, hidden vector, or learned score. Values are
stored only as record payloads and read only after a record is selected.

- Full-history scan persists compact records, inspects the full history, and
  resolves the exact address among utility-eligible records.
- Exact structured memory persists every compact record plus an eligible
  address-to-record-ID index. Its bounded query working set is the indexed
  address bucket, including temporal versions.
- Conventional retrieval persists every compact record plus a utility index,
  scores only utility-eligible records by the frozen two-attribute rule, and
  returns at most 16.
- Recent/FIFO/random retain compact fields actually needed after ingestion;
  their persistent and working bytes no longer include unused retention
  metadata.

Every record and index reference is charged in canonical serialized bytes.
Critical recall for bounded retrieval is target presence in the returned
candidate set.

## Corrected verdict semantics

Thresholds and terminal names are unchanged. Bounded advantage is impossible
if any included bounded conventional system reaches the capability threshold.
Conventional Pareto dominance is checked for each bounded conventional system
at every history size against DMC on:

```text
answer accuracy (within 0.01)
persistent record count
persistent serialized bytes
working-set records (and <=16)
working-set serialized bytes
records inspected at query
retrieval/index operations
ingestion + query wall time
learned forward calls
historical training requirement
```

The terminal is `DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES` if at least one
included conventional system is no worse on every listed dimension. Timing is
still a single measured pass and is interpreted only when the difference is
large enough that the inequality is not marginal.

## Frozen boundaries

Run 3 does not change DMC code, checkpoints, parameters, features, candidate
capacity, cases, case counts, history sizes, training accounting, thresholds,
the Run 2 all-history scorer adapter, or any prior artifact. It adds tests for
authorized utility alias filtering, bounded critical-recall semantics, compact
recent-window state, and inclusion of the recent window in dominance logic.

Run 3 is the final protocol-correction run. Any further implementation or
accounting failure is preserved and reported rather than repaired silently.
