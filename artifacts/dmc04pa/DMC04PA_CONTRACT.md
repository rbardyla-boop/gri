# DMC-04P-A — Fixed Decoder Interface Amendment

Status: **STRUCTURAL PREREGISTRATION ONLY; NO EVIDENCE TRAINING**

DMC-04A hidden memory vectors are frozen seed-1337 DMC-01 representations.
DMC-04P-A fixes the downstream decoder to that native seed-1337 processor for
all five future retrieval seeds. It supersedes only the original processor
pairing clause; it does not regenerate vectors, align latent spaces, change
the retriever, or change any metric, gate, optimizer, or evidence seed.

## Fixed interface

```text
retrieval seed 1337 ─┐
retrieval seed 1338 ─┤
retrieval seed 1339 ─┼─> frozen DMC-01 exact seed-1337 decoder
retrieval seed 1340 ─┤
retrieval seed 1341 ─┘
```

The decoder checkpoint is `artifacts/dmc01/checkpoints/exact_seed1337_final.pt`
with SHA-256 `4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6`.
It is frozen, has zero trainable parameters, and is the only decoder loaded.

## Structural gates

Every stored hidden vector in DMC-04A train, IID, and extrapolation datasets
must decode to its oracle answer through the fixed processor. The symbolic
oracle must achieve retrieval Hit@1 and final-answer accuracy of 1.0 on every
split. The matcher remains the exact 128-parameter factorized model with
`W_A: 8x8` and `W_B: 8x8`; only those parameters may enter a future optimizer.

The future DMC-04 protocol remains unchanged: 80 epochs, batch size 64,
AdamW, learning rate `1e-2`, weight decay `0`, gradient clip `1.0`, CPU with
Torch threads `1`, stateless SHA-256 ordering, seeds `1337..1341`, and all
original retrieval/answer metrics and gates. No evidence training is executed
in this amendment.

## Terminal states

- `DMC_04PA_FIXED_DECODER_PREREGISTERED`
- `DMC_04PA_DECODER_INVALID`
- `DMC_04PA_BENCHMARK_INVALID`
- `DMC_04PA_RETRIEVER_INVALID`
- `DMC_04PA_EVIDENCE_INVALID`
- `DMC_04PA_INVALID`
- `DMC_04PA_REPAIR_REQUIRED`

The original `DMC_04_INVALID` result remains preserved as the correct terminal
state of the superseded DMC-04 protocol.
