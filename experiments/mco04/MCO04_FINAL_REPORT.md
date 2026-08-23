# MCO-04 — OPAQUE REAL-TELEMETRY REPLICATION GATE

## Claim under test

A transparent compiler can reduce append-only incident telemetry to at most 16 auditable records while retaining root-cause localization quality on unseen executions of service/fault strata represented during engineering.

## Check

Frozen RCAEval RE3 replication: 63 opaque scientific incidents across three systems, direct and model-mediated compiler outputs, three mechanical controls, hybrid retrieval, a 20,000-byte safe-context control, fresh stability repeats, and content-addressed replay.

Documentation erratum: the frozen report renderer retained a pre-freeze “24 KB” label. The frozen configuration, contract, requests, and receipts all used 20,000 UTF-8 prompt bytes; only this prose label was corrected after finalization. The frozen methodology source and every scientific artifact remain unchanged.

| Method | Root-cause top-1 | Top-3 / fault exact |
|---|---:|---:|
| transparent compiler | 100.00% | 100.00% top-3 |
| best mechanical control (single_feature_robust) | 31.75% | — |
| model over compiler packet | 100.00% | 0.00% fault |
| best reasoned control (max_context) | 26.98% | — |

| Inference path | Prompt tokens | Output tokens | Model wall | Online query wall |
|---|---:|---:|---:|---:|
| compiler packet | 77,930 | 9,858 | 738.96s | 738.96s |
| hybrid RAG-16 | 112,630 | 8,590 | 662.82s | 687.76s |
| maximum safe context | 429,421 | 9,055 | 1168.61s | 1168.69s |

Hybrid ingestion used 777 embedding calls and 22,661,620 embedding input tokens. Direct compiler ingestion took 8.14s across the scientific set.

## Verdict — PASS

`MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE`

## Criteria

- integrity_pass: **PASS**
- compiler_quality: **PASS**
- provenance: **PASS**
- capacity: **PASS**
- compression: **PASS**
- direct_compiler_gate: **PASS**
- packet_quality: **PASS**
- stability_pass: **PASS**
- bounded_inference_advance: **FAIL**
- conventional_dominates: **FAIL**
- packet_hybrid_quality_equivalent: **FAIL**
- packet_max_context_quality_equivalent: **FAIL**
- packet_hybrid_cost_win: **FAIL**
- packet_max_context_cost_win: **FAIL**
- semantic repeat agreement: 100.00%
- median raw-to-packet byte reduction: 1331.7×
- minimum case reduction: 215.2×

## Assumption register

- Verified: deterministic telemetry staging, source hashes, opaque label separation, exact packet recomputation, 16-record capacity, held-out-run quality, model receipts, stability, and replay on the pinned benchmark.
- Not verified: unseen service/fault strata, organic production incidents, counterfactual causality, changing schemas, concurrent operations, access control, operator usefulness, deployment economics, or prospective impact.
- The scientific split repeats every engineering service/fault stratum. It measures telemetry-run replication, not broad incident generalization.
- The public index exposes labels. The holdout is protected by frozen executable isolation and a literal-leak audit, not by experimenter ignorance of ground truth.
- RCAEval RE3 is fault-injection telemetry. Benchmark success can support mechanics but cannot establish market value or societal impact.

## Credit assignment

The transparent compiler receives credit only for direct root-cause ranking, bounded auditable evidence, and measured compression. The frozen reasoner receives separate credit only for any improvement over that direct ranking. Retrieval and maximum-context controls receive the same raw modalities. DMC and learned retention receive no credit in this gate.

## Verification gap

This is self-verified public-benchmark evidence with frozen replay, not independent replication. The benchmark repeats known strata and exposes an alert timestamp. A disjoint workload with held-out structures, followed by an independently operated prospective pilot, remains necessary.

## Stop/continue

Continue only to a preregistered disjoint-workload gate; do not claim product or world impact from this result.

## Maturity status

Replicated benchmark mechanism; pre-product and pre-impact.

Historical accounting remains explicit: DMC used 10,880 reconstructed optimizer steps, and its wall-time, energy, and dollar training cost remain `TRAINING_COST_UNKNOWN`. MCO-04 performs zero optimizer steps; pretrained-model training cost is unknown, not zero.
Local billed API cost is $0.00; this is not a claim of zero compute, energy, hardware, or opportunity cost. No dollar estimate is reported without a defensible rate.

## Integrity checks

- freeze: **PASS**
- preflight: **PASS**
- opacity: **PASS**
- scientific_case_count: **PASS**
- mechanical_scorer_guard: **PASS**
- mechanical_score_count: **PASS**
- mechanical_scoring_binding: **PASS**
- mechanical_replay_count: **PASS**
- mechanical_replay_scorer_guard: **PASS**
- reasoning_case_count: **PASS**
- reasoning_scoring_binding: **PASS**
- reasoning_scorer_guard: **PASS**
- reasoning_shared_client_contract: **PASS**
- reasoning_replay_count: **PASS**
- reasoning_replay_scorer_guard: **PASS**
- reasoning_replay_shared_client_contract: **PASS**
- reasoning_call_order_balanced: **PASS**
- reasoning_replay_call_order_balanced: **PASS**
- replay: **PASS**
- live_receipts: **PASS**
- replay_receipts: **PASS**
- stability_receipts: **PASS**
- mechanical_live_recomputation: **PASS**
- mechanical_replay_recomputation: **PASS**
- retrieval_integrity: **PASS**
- max_context_below_limit: **PASS**
- stability_selection: **PASS**
- stability_scorer_guard: **PASS**
- stability_seal: **PASS**
- stability_outputs: **PASS**
- stability_citations: **PASS**
