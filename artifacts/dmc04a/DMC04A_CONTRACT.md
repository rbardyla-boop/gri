# DMC-04A — Associative Retrieval Benchmark

Status: **BENCHMARK ONLY; NO LEARNED RETRIEVAL; NO TRAINING**

## Claim under test

DMC-04A is a deterministic, capacity-bounded associative-retrieval exam.
The correct record is physically present in at most 16 candidates, but the
final query uses a disjoint query codebook rather than the exact write-side
address. A symbolic oracle can retrieve the correct record, while exact raw
token matching and single-attribute controls cannot.

Retention is held fixed by construction: no case asks for an evicted record.
The future DMC-04 learned-retrieval experiment must use these candidates with
perfect DMC-02 retention or a preconstructed candidate set. DMC-03 learned
retention is not used here.

## Frozen address and splits

The latent benchmark-only address is `(A, B)` with `A,B in {0,...,7}`.
Write tokens are `write_A_token_n` and `write_B_token_n`; query tokens are
`query_B_token_n` and `query_A_token_n`. The codebooks and attribute order are
disjoint, so exact token equality cannot solve the task.

Training uses the checkerboard partition `(A+B) mod 2 == 0`; extrapolation
uses the held-out partition `(A+B) mod 2 == 1`. Every atomic A and B value is
present in the training partition. IID uses the training composition regime
with fresh deterministic cases.

Families are alias retrieval, compositional retrieval, hard negatives,
current/history version retrieval, and irrelevant cue noise. All candidate
sets contain at most 16 physical records. The query contains no answer value,
record ID, or logical-key object. Logical keys and answer labels exist only in
the separate oracle projection.

The stored neural value is produced by the frozen DMC-01 exact processor
(seed 1337 checkpoint); no DMC-04A model is trained or modified. The final
answer oracle passes the selected hidden vector through that frozen processor.

## Future primary metrics

```text
P_retrieval = mean(ALIAS16_H1, COMP16_H1, HARD16_H1,
                   CURRENT16_H1, HISTORY16_H1, NOISE8_H1, NOISE32_H1)
P_answer    = mean(ALIAS16_A, COMP16_A, HARD16_A,
                   CURRENT16_A, HISTORY16_A, NOISE8_A, NOISE32_A)
```

These metrics are frozen for DMC-04P/DMC-04. Retrieval Hit@1 and final answer
accuracy are recorded separately; answer accuracy alone is not sufficient.

## Controls and terminal states

The benchmark records a symbolic oracle, a deterministic random selector,
exact-token matching, A-only/B-only controls, and a query-only answer-prior
control. The symbolic oracle must achieve 1.0 retrieval and final answer
accuracy. Query-only must remain at the balanced 1/8 prior. At extrapolated
hard negatives, each single-attribute control must be at least 0.40 below
oracle Hit@1. Exact-token Hit@1 must remain at or below 0.10 on the 16-record
extrapolation conditions.

Terminal states:

- `DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS`
- `DMC_04A_MEMORY_LEAK`
- `DMC_04A_ADDRESS_LEAK`
- `DMC_04A_ORACLE_INVALID`
- `DMC_04A_RETRIEVAL_SIGNAL_WEAK`
- `DMC_04A_INVALID`
- `DMC_04A_REPAIR_REQUIRED`

This unit stops after its validated benchmark commit. It does not implement a
learned retriever, attention, similarity, neural key projection, training,
evidence seeds, DMC-04P, or DMC-04B.
