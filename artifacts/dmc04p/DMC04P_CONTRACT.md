# DMC-04P — Factorized Associative Retrieval Preregistration

Status: **STRUCTURAL PREREGISTRATION ONLY; NO EVIDENCE TRAINING**

## Claim under test

The frozen DMC-04A descriptor interface is compatible with a 128-parameter
factorized associative matcher that learns independent atomic write/query
correspondences for A and B. DMC-04P defines the future retrieval experiment;
it does not measure retrieval accuracy or produce a DMC-04 verdict.

## Frozen DMC-04A interface

The raw write descriptor has exactly `tokens` and `attribute_order` fields.
Its order is A,B and its codebooks are `write_A_token_0..7` and
`write_B_token_0..7`. The raw query descriptor has exactly `tokens`,
`attribute_order`, and `noise_token_count`; its order is B,A and its codebooks
are `query_A_token_0..7` and `query_B_token_0..7`. These vocabularies are
disjoint. The benchmark-only logical key is never passed to the matcher.

The matcher input contains only the query descriptor, CURRENT/HISTORY mode,
as_of_episode, each candidate write descriptor, and creation_episode. It does
not receive hidden values, answers, logical keys, record IDs, case IDs, or
oracle decisions. It scores every candidate in the frozen DMC-04A candidate
set, whose capacity remains at most 16.

## Model class

For each atomic attribute:

```text
score = q_A^T W_A w_A + q_B^T W_B w_B
W_A, W_B in R^(8x8)
```

There are exactly 128 trainable parameters, no bias, no MLP, no whole-pair
embedding, no cross-attribute term, and no attention. Each atomic matrix can
represent an arbitrary correspondence between its disjoint query and write
codebooks. The sum distinguishes complete A+B matches from A-only and B-only
matches.

For versioned records, the zero-parameter resolver first selects the highest-
scoring raw descriptor group, then chooses the latest eligible creation
episode for CURRENT or HISTORY. Equal-score ties use ascending SHA-256 of the
raw frozen record ID. Record IDs are resolver metadata, never matcher input.

## Future evidence protocol

Training uses only frozen DMC-04A TRAIN cases, group-level retrieval
cross-entropy, 80 epochs, complete-case batches of 64, AdamW at 1e-2, zero
weight decay, gradient clip 1.0, CPU, and one Torch thread. Ordering is
`SHA256("DMC04_ORDER|" + seed + "|" + epoch + "|" + case_id)` sorted ascending.
Evidence seeds are 1337–1341. No evidence seed is executed in DMC-04P.

The five DMC-01 processors are frozen and paired by seed for the later final
answer path. They are not in the retrieval optimizer. Hidden values are used
only after retrieval by the frozen processor.

Future primary metrics and gates are frozen in `DMC04P_CONFIG.json`; this
preregistration does not report them.

## Terminal states

- `DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED`
- `DMC_04P_MODEL_CLASS_UNRESOLVED`
- `DMC_04P_RETRIEVAL_LEAK`
- `DMC_04P_PROCESSOR_INVALID`
- `DMC_04P_CAPACITY_INVALID`
- `DMC_04P_INVALID`
- `DMC_04P_REPAIR_REQUIRED`

This unit stops after its structural commit. It does not train retrieval,
measure scientific accuracy, integrate DMC-03 retention, or begin DMC-05.
