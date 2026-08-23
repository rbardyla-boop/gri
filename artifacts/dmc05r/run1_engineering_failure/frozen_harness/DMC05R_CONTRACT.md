# DMC-05R — Recency Confound Repair

Status: preregistered before implementation and execution.

## Claim under test

On the 592 frozen DMC-04B-A/DMC-05A source cases, frozen DMC-04B will preserve
target records and answers when useful information is separated from stream
recency by deterministic tails of certified irrelevant writes. The direct
counterfactual is Recent-16. Architecture-level selection credit requires a
material win over an equally informed, transparent, bounded utility selector.

This is a benchmark-only experiment. No DMC checkpoint, model weight,
threshold, capacity, feature, source record, query, answer, or oracle field may
change in the primary experiment.

## Frozen source and variants

The source is the DMC-04B-A dataset manifest with SHA-256
`ee4afa55326205030a8600b079a0a484b6bfa39312d6127a80633e00c93274fc`.
The DMC-05A filter selects 592 cases at loads 32, 64, 128, 256, and 1024.

For each source case and requested tail `k` in `0, 8, 16, 32, 64, 256`, the
harness may emit a variant only when at least `k` records satisfy every clause
of the frozen irrelevant predicate:

1. The record ID is absent from `oracle_view.records` and is not the target.
2. Its entity is absent from every declared scope event.
3. It neither supersedes another record nor is referenced by another record's
   `supersedes` field.
4. Its salience is not `HIGH`.
5. Its frozen retention feature vector is exactly `[0.0, 0.0]`.

The transformation selects the last `k` certified records in source order,
removes them, and appends them in the same order. This preserves the relative
order of every protected record and of every certified-irrelevant record. It
changes only protected-versus-irrelevant stream position. All record payloads,
creation episodes, supersession links, metadata, neural views, oracle views,
queries, targets, and answers remain byte-for-byte unchanged.

The preregistered variant counts are:

| Tail | Variants |
|---:|---:|
| 0 | 592 |
| 8 | 512 |
| 16 | 512 |
| 32 | 416 |
| 64 | 256 |
| 256 | 88 |
| **Total** | **2,376** |

Insufficient cases are recorded as skipped; they are never padded or replaced.
Tails 16, 32, 64, and 256 form the primary adversarial subset. Tail 8 is a
dose-response diagnostic and tail 0 is the frozen anchor.

## Required systems and information parity

The systems are Recent-16, the historical frozen FIFO-16 control, deterministic
Random-16, exact structured all-history indexing, conventional all-history
retrieval with a 16-record query set, transparent utility-aware indexing with a
hard 16-record persistent budget, and frozen DMC-04B for paired seeds 1337–1341.

The historical `frozen_fifo_16` control keeps the first 16 writes and rejects
later writes. An evict-oldest FIFO window is exactly Recent-16 and is therefore
not duplicated under another label. Random-16 is keyed by source case ID and
record ID so reordering cannot change its selected set.

The transparent selector receives exactly the frozen DMC retention inputs:
`mission_membership`, `high_salience`, and the same active-scope transitions.
The utility classifier/scorer in neither selector may receive query fields,
target identity, answer, value, write descriptor, hidden value, logical key,
record ID, case ID, or oracle decision. Record ID is available only to the
deterministic tie-break resolver, exactly as in frozen DMC-04B. Both use the
same supersession and utility-change lifecycle semantics. The transparent
selector ranks records satisfying either explicit utility feature before
records satisfying neither, with the same record-ID hash tie break and a hard
capacity of 16. Query and answer evaluation then use each system's declared
frozen retrieval path.

## Integrity gates

Any failure below produces `DMC_05R_ACCOUNTING_INVALID` before scientific
interpretation:

- all DMC-04B, DMC-05A, source-data, checkpoint, contract, config, runner, and
  test anchors match;
- source and variant counts match the preregistration;
- each transformation passes the multiset, payload, protected-order,
  irrelevant-order, trailing-tail, answer, target, query, metadata, and
  supersession invariants;
- the DMC execution optimization matches the frozen DMC-05A receipts on
  persistent-set hash, selected record, capability fields, and logical score
  evaluations for all 592 tail-zero cases and all five seeds; it additionally
  matches ordered retained IDs and retrieval/answer behavior from a direct
  frozen-retainer execution on the lexicographically first and last valid
  variant at each nonzero tail for all five seeds;
- all bounded systems remain at or below 16 persistent records and all-history
  systems retain exactly the source load;
- no optimizer, backward pass, threshold adjustment, model mutation, feature
  change, archive, spill, or hidden external state occurs;
- deterministic outputs replay exactly; and
- all resource and training fields are present, including 10,880 reconstructed
  heterogeneous optimizer steps and `TRAINING_COST_UNKNOWN` for historical
  wall time, energy, and dollar cost.

## Capability and outcome gates

Tail-zero Recent-16, transparent indexing, and DMC-04B must each retain at least
0.99 answer accuracy; exact structured and conventional retrieval must retain
at least 0.99 accuracy on every tail.

For the pooled primary adversarial subset, DMC survives non-recency when mean
critical recall and answer accuracy are each at least 0.90 and its critical
recall advantage over Recent-16 is at least 0.50. Strong capability is 0.99.
Recent-16 collapse is recorded when primary critical recall is at most 0.01.

Mechanical terminal precedence is:

1. `DMC_05R_ACCOUNTING_INVALID` for any integrity failure.
2. `DMC_05R_RECENCY_ONLY_FAILURE` when DMC fails either 0.90 survival floor or
   fails to beat Recent-16 critical recall by 0.50.
3. `DMC_05R_SELECTION_ADVANTAGE` only when DMC has strong capability and beats
   transparent indexing by at least 0.05 in both critical recall and answer
   accuracy under the same 16-record budget.
4. `DMC_05R_TRANSPARENT_INDEX_DOMINATES` when DMC survives, transparent indexing
   has strong capability within 0.01 of DMC, and transparent indexing is no
   worse in persistent records/bytes, working records/bytes, query inspections,
   online wall time, learned forward calls, and historical training requirement.
5. `DMC_05R_NONRECENCY_RETENTION_ADVANCE` when DMC survives and materially beats
   recency but neither selection advantage nor transparent dominance holds.

The non-recency retention finding is retained as a subordinate gate even when
the terminal state is transparent-index dominance. No composite score may hide
an absolute resource dimension.

## SURPRISE_DEPENDENCY exploratory subset

Twenty-four extrapolation mission-set cases—eight each at loads 128, 256, and
1024—form a separate nonterminal subset. After ordinary ingestion, one old
certified-irrelevant record becomes useful through an explicit late scope
event, and a history query requests that record. DMC and transparent indexing
receive the same event at the same time. All-history systems may consult their
already-stored history; bounded systems may not resurrect discarded state.

This subset asks whether retention can preserve information whose future
utility was not visible when written. Its result cannot alter the DMC-05R
terminal state, and failure does not authorize redesign, retraining, new
features, threshold changes, or capacity changes.

## Stop rule

DMC-05A remains terminal. DMC-05B, real-language evaluation, tokenizer
accounting, and model-inference cost work remain blocked unless DMC-04B survives
the transparent utility-index comparison. A transparent-index dominance result
is the branch-stop signal for learned retention in this synthetic family.
