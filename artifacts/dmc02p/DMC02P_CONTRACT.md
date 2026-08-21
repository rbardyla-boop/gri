# DMC-02P — 16-Slot Bounded Exact-Retention Preregistration

Status: **PREREGISTERED; STRUCTURAL CONTROL ONLY; NO SCIENTIFIC EVALUATION**

## Scientific question

Can the DMC-01 learned hidden representations remain usable when physical
storage is capped at exactly 16 hidden records, while retention decisions and
exact addressing remain perfect? This is an upper-bound control that removes
unlimited storage but does not yet learn importance or retrieval.

The future DMC-02 evidence unit must use the five frozen DMC-01
`EXACT_MEMORY` checkpoints without retraining. This preregistration performs
no accuracy evaluation and executes no evidence seeds.

## Frozen processor

The trainable processor is unchanged:

```text
ImmutableRelationAnchorReasoner
hidden_dim = 49
message_dim = 51
train_depth = 4
trainable parameters = 30,912
```

The memory controller adds zero trainable parameters.

## Hard physical budget

Every controller mode has exactly 16 physical record slots. The runtime
invariant is checked after every scope and write event:

```text
len(memory) <= 16
```

There is no archive, overflow buffer, compressed spill, disk side channel, or
recomputation from raw prior episodes.

## Memory modes

1. `EXACT_RETENTION_16`: mission membership, salience, explicit mission
   updates, supersession metadata, and creation episode are the only
   retention inputs.
2. `FIFO_16`: deterministic first-in-first-out eviction.
3. `RANDOM_16`: the DMC-02A deterministic reservoir rule with independent
   seed `20260202`.

All three modes use the same frozen neural processor. None has trainable
memory-management parameters.

The exact policy receives a metadata-only `RetentionMetadata` object. It has
no answer value, hidden vector, final query, case ID, future event, or oracle
answer. The final queried key is never supplied to retention.

## Retention and retrieval

Every write first produces the DMC-01 hidden representation. The authorized
metadata policy then decides whether that record is stored. Irrelevant records
may be discarded immediately. Utility-change eviction occurs only after the
explicit mission-update event. Supersession retains both historical and
current records when both are query-eligible.

Retrieval is exact `(entity, field)` lookup. Current retrieval returns the
latest retained record; history retrieval returns the latest retained record
whose creation episode is no later than `as_of_episode`. No learned search,
attention, cosine similarity, semantic address, compression, or quantization
is present.

## Future evidence protocol

The future unit uses DMC-02A data byte-for-byte and the frozen primary metric:

```text
P_bounded = mean(
    M256, M1024,
    SAL256, SAL1024,
    SUP_current_1024, SUP_history_1024,
    SHIFT,
    FLOOD512, FLOOD1024
)
```

`EXACT_RETENTION_16` advances only if all of the following pass:

- mean `P_bounded >= .95`;
- mean `M1024 >= .95`;
- mean `SAL1024 >= .95`;
- mean `SUP_current_1024 >= .95`;
- mean `SUP_history_1024 >= .95`;
- mean `SHIFT >= .95`;
- mean `FLOOD1024 >= .95`;
- `P_bounded >= .90` for all five checkpoints;
- mean exact-minus-FIFO primary metric `>= .40`;
- mean exact-minus-random primary metric `>= .40`.

These gates are recorded now and are not evaluated in DMC-02P.

## Structural checks performed here

- 16-slot invariant and absence of overflow fields;
- metadata-only retention firewall;
- FIFO and deterministic random behavior;
- exact current/history retrieval;
- supersession preservation;
- utility-update eviction timing;
- hidden-vector identity before and after storage;
- compatibility with all five frozen DMC-01 checkpoints;
- DMC-02A, DMC-01, and WORLD-0 identity/hash boundaries.

## Explicit non-actions

This unit performs no optimizer steps, backward passes, retraining, evidence
evaluation, benchmark scoring, learned retention, learned eviction, learned
retrieval, DMC-03 work, or language experiments.

## Terminal state

`DMC_02P_PREREGISTERED`
