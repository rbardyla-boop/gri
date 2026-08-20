# DMC-01P — Exact Episodic Memory Preregistration

Status: **PREREGISTERED; STRUCTURAL IMPLEMENTATION ONLY; NO SCIENTIFIC TRAINING**

## Purpose

DMC-01 tests whether the surviving RRI processor can store a learned hidden
representation in a deterministic exact-address ledger and later use that
representation. The ledger supplies the exact `(entity, field)` address but
never supplies a symbolic answer.

The current RRI foundation is frozen as the parameter-neutral immutable-anchor
processor:

- `ImmutableRelationAnchorReasoner`
- `hidden_dim=49`, `message_dim=51`
- `h0 = initialize(event_graph)`
- `a = clone(h0)` is write-protected for the current event
- four shared recurrent steps
- mutable-state-only readout
- `30,912` trainable parameters

The DMC adapter is deterministic and has zero trainable parameters. It maps a
write value to one of the eight existing input relation channels, builds a
query/noise graph with no relation channels, and does not encode entity or
field into the neural graph. The existing RRI node encoder, message function,
gated update, normalization, anchor path, and readout remain shared.

## Exact memory semantics

The per-case ledger is append-only and reset between cases. Each record stores
exactly:

```text
memory_id, entity, field, creation_episode, supersedes,
source_episode, hidden_value
```

`hidden_value` is the target-node hidden vector after the four-step write
episode. It is copied without compression, quantization, averaging, capacity
limiting, or forgetting. The record contains no answer string, label, one-hot
answer, or oracle result.

Current queries retrieve the latest record at `(entity, field)`. History
queries retrieve the latest record at that key with
`creation_episode <= as_of_episode`. Old records are retained.

The neural query path receives only the retrieved hidden vector. The symbolic
ledger performs address selection; it never calls the DMC-00 oracle.

## Matched controls

`EXACT_MEMORY` and `NO_MEMORY` use the same RRI module topology and trainable
parameters. The no-memory control processes write events and discards their
states; its query path accepts only the current query event and no ledger
record. The structural seed is `9091`. Evidence seeds `1337`–`1341` are frozen
but are not executed in DMC-01P.

The later `SHUFFLED_MEMORY` evaluation control uses a deterministic cyclic
mapping to the lexicographically next case within the same balanced
family/condition group. It is evaluation-only and involves no retraining.

## Future training protocol

DMC-00 frozen train, IID, and extrapolation datasets are reused byte-for-byte.
Future case batches contain complete episode sequences with one independent
ledger per case slot; episodes are processed in episode order and recurrent
depth is four per event. The preregistered optimizer protocol is 80 epochs,
batch size 16, AdamW, learning rate `3e-3`, weight decay `1e-4`, gradient clip
`1.0`, CPU, and one Torch thread.

The frozen primary metric is:

```text
P_memory = mean(R64, R256, R1024, C256, C1024,
                S_current, S_history, D512, D1024)
```

No scientific accuracy is produced by DMC-01P. The advancement gates are
recorded here before evidence training: train and IID means at least `.95`,
`P_memory >= .90`, exact-minus-no-memory `P_memory >= .60`, mean `R1024 >=
.90`, mean `C1024 >= .90`, current/history supersession means at least `.95`,
mean `D1024 >= .90`, exact memory wins paired `P_memory` on `5/5` seeds, and
the shuffled-memory mean is at least `.40` below exact memory.

## Stop boundary

DMC-01P stops after structural validation and one terminal receipt. It does
not implement training, evidence runs, bounded memory, learned retrieval,
consolidation, forgetting, compression, or dimensional memory.
