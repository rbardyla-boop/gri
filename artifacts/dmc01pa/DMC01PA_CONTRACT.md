# DMC-01P-A — Training Semantics Amendment

Status: **PREREGISTERED; STRUCTURAL VALIDATION ONLY; NO SCIENTIFIC TRAINING**

This amendment supplements the historical DMC-01P preregistration. It freezes
only the training semantics that were previously missing. It does not change
DMC-00, WORLD-0, the RRI architecture, ledger semantics, memory injection,
parameter counts, evidence seeds, budget, primary metric, gates, or shuffle
mapping.

## Supervision and loss

Each complete DMC case produces exactly one supervised prediction: the final
query. Writes and noise events have no auxiliary losses. The harness alone
maps `case["answer"]` to the index in the frozen DMC-00 `VALUES` tuple.

For logits `z` and target `y`, the individual loss is exactly:

```python
F.cross_entropy(z.unsqueeze(0), y.unsqueeze(0), reduction="mean")
```

For a batch of `B` complete cases, `batch_loss` is the arithmetic mean of the
`B` case losses. There is no condition/class/delay weighting, auxiliary loss,
reconstruction loss, contrastive loss, or additional regularizer.

## Complete-case batching and optimizer cadence

Batch size means **16 complete cases**, not episodes. Every case is processed
from its first episode through its final query, with a fresh ledger reset at
the start of the case. No case is truncated and no ledger state crosses case
boundaries.

Each batch performs exactly:

```python
optimizer.zero_grad(set_to_none=True)
batch_loss.backward()
clip_grad_norm_(model.parameters(), 1.0)
optimizer.step()
```

There is one optimizer step per complete case batch, no accumulation across
batches, and no step inside an episode, write, or query. A final short batch is
averaged over its actual case count. The optimizer is AdamW with learning rate
`3e-3`, weight decay `1e-4`, CPU, one Torch thread, and no scheduler.

## Stateless case ordering

For seed `s`, zero-based epoch `e`, and case ID `C`, the order key is the raw
digest:

```text
SHA256("DMC01_ORDER|" + str(s) + "|" + str(e) + "|" + C)
```

Cases are sorted by ascending digest bytes and split sequentially into batches
of 16. The exact/no-memory pair uses the same ordered IDs and boundaries. No
mutable global RNG state determines training order. The complete order
manifest for seeds `1337`–`1341` and epochs `0`–`79` is generated and hashed
by this amendment, without training those seeds.

## Autograd semantics

During exact-memory training, `hidden_value = write_state.clone()` remains
attached to autograd. No `detach`, `detach_`, or `torch.no_grad` is applied to
the stored write vector. The final query loss may backpropagate through the
retrieved vector into the write-event computation and shared RRI parameters.

Only the retrieved record needs to remain connected to the final loss. Unused
records and noise states receive no auxiliary loss. Case graphs are released
after the batch step; `retain_graph=True` is not used.

The no-memory control uses identical weights, ordering, batching, loss,
optimizer, cadence, and epochs, but discards write states. Its query has no
prior-write state or gradient path.

## Checkpoint/resume semantics

Checkpoints are valid only immediately after a complete optimizer step and
record model state, optimizer state, seed, completed epoch, next batch index,
Python/NumPy/PyTorch RNG states, training config, source commit, DMC-00
identity, final loss, and metrics. Resume reconstructs the stateless current
epoch order and continues at the recorded next batch without repeating or
skipping a batch.

No scientific training, evidence seed, accuracy result, or DMC-01 verdict is
produced by DMC-01P-A. Its sole terminal success state is
`DMC_01PA_PREREGISTERED`.
