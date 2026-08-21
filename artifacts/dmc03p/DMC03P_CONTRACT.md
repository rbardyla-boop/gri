# DMC-03P — Learned Selective Retention Preregistration

Terminal state: `DMC_03P_LEARNED_RETENTION_PREREGISTERED`

This artifact freezes the structural implementation and protocol only. No
scientific retention training, evidence-seed optimization, DMC-03 benchmark
accuracy, or learned retrieval is authorized in DMC-03P.

## Frozen system

The five DMC-01 EXACT_MEMORY processors (seeds 1337–1341) are loaded read-only
and remain `ImmutableRelationAnchorReasoner` processors with hidden dimension
49, message dimension 51, train depth 4, and 30,912 parameters. Only the
three-parameter affine retention scorer is trainable in the later DMC-03 run.
Physical memory contains at most 16 `MemoryRecord` objects after every
decision. There is no overflow, archive, spill, compression, replay, or
secondary store. Retrieval remains exact `(entity, field)` current/history
retrieval from DMC-02.

## Frozen retention model

The feature map is exactly `[mission_membership, high_salience]`. Mission
membership is derived from the current active scope and exact entity metadata
for mission-set, supersession, and utility-change families. High salience is
1 only for explicit `HIGH` salience. The scorer is `priority = w dot x + b`.
No hidden value, answer, query, future event, case identity, correctness, or
oracle action is an input. Supersession and creation episode are authorized
metadata fields but are excluded because they are not needed to represent the
frozen DMC-02A admission rule.

At each write, existing retained records plus the candidate are scored and the
highest 16 are retained. Ties are resolved by ascending SHA-256 of
`memory_id`. Explicit scope updates recompute current metadata features. The
future learned policy operates without oracle decisions.

## Future training and evaluation freeze

Later training, if this preregistration passes all structural checks, uses
frozen DMC-02A TRAIN cases only, 40 epochs, batch size 256, AdamW with learning
rate `1e-2`, weight decay `0`, gradient clip `1.0`, CPU Torch threads 1, and
stateless ordering by `SHA256(seed|epoch|training_example_id)`. Loss is mean
`binary_cross_entropy_with_logits` over retention labels only. Processor and
retrieval are not jointly optimized. Evidence seeds are 1337–1341 with paired
DMC-01 checkpoints; no early stopping, scheduler, retry, or search is allowed.

The future primary is unchanged from DMC-02A:
`mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)`.
The preregistered advancement gates are: mean learned primary at least `.90`;
oracle gap at most `.10`; M1024, SAL1024, both supersession metrics, SHIFT,
and FLOOD1024 each at least `.90`; learned primary at least `.85` on all five
seeds; learned minus FIFO at least `.60`; learned minus random at least `.60`;
and learned minus shuffled-metadata at least `.40`. Retention accuracy,
precision, recall, and F1 remain diagnostics, not substitutes for the primary.

## Structural stop rule

This preregistration stops here. Any failure is terminally classified as
`DMC_03P_MODEL_CLASS_UNRESOLVED`, `DMC_03P_RETENTION_LEAK`,
`DMC_03P_PROCESSOR_INVALID`, `DMC_03P_CAPACITY_INVALID`,
`DMC_03P_INVALID`, or `DMC_03P_REPAIR_REQUIRED` as applicable. A later
scientific run must be a separate evidence commit.
