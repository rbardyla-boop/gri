# MCO-02 — LANGUAGE / INFERENCE BOUNDARY

## Claim under test

Complete externally stored natural-language history can preserve equivalent task quality with bounded model-visible state and materially lower total expensive inference than context-heavy or conventional retrieval after ingestion is amortized.

## Check

Self-verified frozen local-model experiment using `llama3.1:8b` blob `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`, the embedded `llama-bpe` tokenizer, 8 histories, 32,200 language events, 64 questions, six systems, one complete live inference run, a stratified live determinism repeat, and two byte-identical replays from frozen raw responses.

| System | Scored | Answer | Critical recall | Provenance | Max visible records | Max prompt tokens | Query calls | Query expensive units |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full_context | 16/64 | 18.75% | 100.00% | 0.00% | 100 | 7559 | 1.00 | 7,933.2 |
| recent_window | 64/64 | 0.00% | 3.93% | 0.00% | 16 | 1476 | 1.00 | 1,773.6 |
| rolling_summary | 64/64 | 1.56% | 5.00% | 0.00% | 16 | 1466 | 1.00 | 1,774.4 |
| conventional_rag | 64/64 | 0.00% | 31.22% | 0.00% | 16 | 1394 | 1.00 | 1,644.6 |
| structured_exact_planner | 64/64 | 81.25% | 93.26% | 42.19% | 5 | 527 | 1.00 | 732.4 |
| iterative_need_retrieval | 64/64 | 81.25% | 95.42% | 40.62% | 6 | 527 | 3.39 | 1,577.8 |

Shared extraction precision/recall: **95.33%** over 32,200 records. Full-context infeasibility is excluded from accuracy, not counted as failure.

## Verdict — FAIL

`MCO_02_ACCOUNTING_INVALID`

Planner answer accuracy was 81.25%; iterative accuracy was 81.25%; conventional RAG accuracy was 0.00%. Planner and iterative consume the identical extraction artifact per history.

## Criteria

- Frozen code, corpus, model, and tokenizer identity: **PASS**
- Exact population, context caps, failure reconciliation, and shared extraction: **PASS**
- Live response stability ≥95%: **FAIL** (82.53%)
- Two byte-identical frozen-response replays: **PASS**
- Extraction quality gate: **PASS**
- Structured quality gate: **FAIL**
- Conventional RAG dominance gate: **FAIL**
- Extraction-cost dominance gate: **FAIL**
- Transparent planner cheaper than iterative acquisition: **PASS**

## Assumption register

- **Verified here:** renderer semantic preservation, opaque provenance IDs, shared extraction identity, local model/token accounting, bounded query contexts, failure attribution, and deterministic replay.
- **Checkable but unchecked:** open-domain extraction, approximate/vector embedding variants, other models/tokenizers, concurrency, mutable stores, security boundaries, energy use, and real user workloads.
- **Unfalsifiable here:** future adoption and societal impact.
- The extraction boundary is hybrid: explicit IDs, values, sources, and updates are scaffolded deterministically; the model normalizes relation language. Credit must not be generalized to unconstrained document understanding.
- The full-context deployment limit is 32,768 tokens on this hardware even though the model metadata advertises a 131,072-token native context.
- Local inference has zero billed API cost; no fictional USD estimate is reported. Token units, calls, and wall time are the measured cost evidence.

## Credit assignment

Credit belongs only to components that survive the frozen nulls. If exact planning matches iterative acquisition more cheaply, the transparent planner receives credit and iterative `NEED(...)` does not. Learned retention, DMC, model strength, scientific novelty, and production economics receive no credit.

## Verification gap

No independent verifier was available, so this is explicitly self-verified. Frozen-response replay validates the harness but is not an independent second model run. The 10% live repeat measures local determinism. Controlled generated language with explicit opaque IDs remains materially easier than real documents.

## Stop/continue

STOP at the frozen terminal verdict and follow only its smallest named repair.

## Is this going to change the world?

**NOT ESTABLISHED.** No evidence in this project establishes that it will change the world. MCO-02 can raise or lower confidence in a mechanism, but societal impact remains a long-horizon, externally contingent claim.

## Maturity status

`MATURE_CONTROLLED_SYNTHETIC_LANGUAGE_EXPERIMENT`; `EARLY_UNVALIDATED_REAL_WORLD_SYSTEM`; `WORLD_IMPACT_CLAIM_NOT_MATURE`
