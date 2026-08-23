# MCO-01 — STORE ALL, THINK SMALL

## Frozen claim

A complete, cheap external event history can support correct reasoning with at most 16 active records, even when a fact's relevance is only exposed by later evidence. MCO-01 tests storage and acquisition, not learned retention.

The experiment is deterministic and synthetic. It does not train or modify DMC, expose utility labels at ingestion, invoke a language model, count tokens, or claim production economics.

## Intervention and controls

The independent variables are history size and acquisition policy. Histories contain opaque, structured events with 2–5-hop delayed dependencies, corrections, renames, supersession, source-ranked contradictions, and unrelated distractors. Every query is asked after the complete history is stored.

Required records are placed randomly subject only to semantic constraints: a replacement follows the record it supersedes, and all records precede the query. The generator must reject any history in which a query's complete critical path fits in a contiguous 16-record window. Records must not contain query IDs, chain IDs, utility labels, answer labels, or target-position hints.

The five frozen systems are:

| System | Persistent history | Active reasoning records | Acquisition |
|---|---:|---:|---|
| Full-history oracle | all | all | all records |
| Recent-16 | final 16 | at most 16 | no retrieval |
| Exact structured lookup | all | at most 16 | transparent index and deterministic graph traversal |
| Conventional one-shot retrieval | all | at most 16 | one query-dependent retrieval call |
| Iterative `NEED(...)` retrieval | all | at most 16 | acquire, inspect, and request the next unresolved key |

Exact structured lookup may traverse the transparent external index, but the reasoner receives only the winning provenance path. Iterative retrieval may retain resolved winning records and temporarily inspect the current key's resolution bundle; both count toward the 16-record peak. One-shot retrieval cannot reformulate after seeing its first result.

All store-all systems receive the same event fields, source-priority policy, and indexes. No system receives expected paths or answers. The oracle's expected active-set violation is descriptive and is not applied to bounded-system acceptance.

## Resolution semantics

Records are keyed by subject and relation. A record explicitly named by a later record's `supersedes` field is inactive. Among remaining contradictory candidates, higher source priority wins; ties resolve to the later stream position and then lexicographic record ID. A `renamed_to` edge is followed before a `depends_on` edge. Terminal entities expose `failure_threshold`; inspection is required when deployment temperature is lower than that threshold.

Provenance is the ordered list of winning record IDs actually used from the query root to the terminal threshold. A coherent answer reached through stale or lower-authority records is wrong.

## Frozen populations and denominators

The generator creates five seeds at each of four history sizes: 100, 1,000, 10,000, and 100,000 records. Every history contains eight queries, with two queries at each dependency length from 2 through 5. This yields 20 histories, 160 queries, and 555,500 stored records before system multiplication.

Every accuracy metric uses all 160 queries unless explicitly grouped by history size, hop count, or family. Temporal/update accuracy is evaluated over each query's keys that contain a correction, supersession, or contradiction; a query with no such key contributes 1.0 only if its selected path is otherwise exact. Critical recall is expected winning path records recovered divided by expected winning path records. Provenance accuracy requires exact ordered-path equality.

## Integrity checks

Before a scientific verdict, the harness must establish all of the following:

1. Exact population counts and seed/load coverage.
2. Unique IDs and valid references.
3. Superseded-before-replacement ordering.
4. Correct answers independently reconstruct from event semantics.
5. No forbidden labels or identifiers occur in records.
6. Every critical path spans more than 16 stream positions and is absent from both the first and last 16 records.
7. Required-record positions cover all stream quartiles in aggregate at every load.
8. All bounded systems peak at no more than 16 active records.
9. Every metric denominator is nonzero and matches the frozen population.
10. Code, configuration, dataset, and run artifacts match their frozen hashes.
11. A second valid run reproduces scientific rows and verdict inputs byte-for-byte after excluding explicitly declared wall-clock fields.

Any failed integrity check produces `MCO_01_ACCOUNTING_INVALID`, not a scientific architecture result.

## Mechanical decision

Verdicts are evaluated in the precedence recorded in `MCO01_CONFIG.json`.

- `MCO_01_EXTERNAL_STORE_FAILS`: neither transparent exact lookup nor iterative acquisition is accurate and stable under the active cap.
- `MCO_01_ONE_SHOT_RETRIEVAL_SUFFICIENT`: conventional one-shot acquisition already matches iterative acquisition.
- `MCO_01_ITERATIVE_ACQUISITION_ADVANCES`: iterative acquisition clears bounded quality gates and materially beats one-shot, especially on 3–5-hop chains.
- `MCO_01_BOUNDED_ATTENTION_ADVANCES`: bounded store-all reasoning works, but neither more specific acquisition conclusion is justified.

`MCO_01_ACCOUNTING_INVALID` overrides every scientific verdict.

## Credit boundary and stop rule

A pass credits the combination of complete structured history, transparent indexing, and bounded acquisition. It does not establish natural-language robustness, tokenizer savings, model inference quality, learned memory value, or production cost advantage.

After the first terminal valid verdict, stop. Language rendering, tokenizer accounting, and model-cost comparison remain blocked unless a bounded store-all system first clears this gate.
