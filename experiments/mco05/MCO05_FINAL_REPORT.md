# MCO-05 — DISJOINT CHANGE-ATTRIBUTION GATE

## Claim under test

A frozen transparent state compiler can select at most 16 auditable incident/change records on an unseen benchmark and enable exact causal-commit attribution better than equally informed conventional controls.

## Check

All 36 RootCauseBench scenarios at pinned commit `0c3c476e4627978dc54b5c047fd488d40561b4e5` were scientific-only. Scenario files were cloned only after method freeze, staged under opaque IDs, model-scored only after prediction seals, repeated on a fresh hash-selected subset, and replayed from content-addressed receipts.

| Method | Exact commit | Adversarial | No-code |
|---|---:|---:|---:|
| compiler candidate coverage | 82.14% | — | — |
| direct compiler top-1 | 30.56% | — | — |
| model over state packet | 33.33% | 0.00% | 12.50% |
| hybrid RAG-16 | 27.78% | 25.00% | 0.00% |
| maximum safe context | 22.22% | 8.33% | 87.50% |

## Verdict — FAIL

`MCO_05_DISJOINT_COMPILER_TRANSFER_FAILURE`

## Criteria

- integrity_pass: **PASS**
- compiler_transfer: **FAIL**
- packet_quality: **FAIL**
- conventional_dominates: **FAIL**
- bounded_inference_advance: **FAIL**
- code-cause candidate recall: 82.14% (23/28)
- packet exact-commit accuracy: 33.33%
- packet Wilson 95% interval: 20.21%–49.67%
- packet advantage over hybrid_rag_16: 5.56%
- fresh semantic stability: 100.00%

## Assumption register

- Verified: pinned source identity, post-freeze staging, static/runtime oracle isolation, exact compiler recomputation, bounded packets, model receipts, scorer binding, fresh repeats, and exact replay.
- Not verified: organic production incidents, live schema drift, access controls, concurrent ingestion, operator usefulness, deployment economics, prospective causality, customer adoption, or independent replication.
- RootCauseBench contains fictional reconstructions and fault injections. It changes task structure but is not a production pilot.
- Public benchmark documentation describes scenario mechanisms. Isolation is executable, not experimenter blinding.
- The local 8B reasoner tests this frozen implementation; a failure does not prove every possible model would fail, but it does falsify the tested product claim.

## Credit assignment

Candidate coverage is credited to transparent selection. Exact commit attribution beyond direct rank is credited to the frozen reasoner. Hybrid RAG and safe context receive the same compiled visible documents and model. DMC, learned retention, and MCO-04's service-localization heuristic receive no credit.

## Verification gap

This remains self-verified public-benchmark evidence. Even a positive result requires a preregistered independently operated prospective incident pilot. A negative result stops the tested state-compiler product branch unless a genuinely new falsifiable mechanism is proposed.

## Stop/continue

Stop the tested product-architecture branch. Preserve the failure taxonomy and do not redesign around scientific labels under the same claim.

## Maturity status

Terminal negative on disjoint change attribution for the frozen implementation; no product or impact claim.

## Accounting

Hybrid ingestion used 285 embedding calls and 559,119 embedding input tokens. The live reasoner used 108 calls. Local billed API cost was $0.00, not zero compute cost.

DMC's 10,880 reconstructed optimizer steps and `TRAINING_COST_UNKNOWN` remain preserved. MCO-05 used zero online optimizer steps; pretrained-model training cost remains unknown and nonzero.

## Integrity checks

- freeze: **PASS**
- preflight: **PASS**
- opacity: **PASS**
- case_count: **PASS**
- mechanical_capacity: **PASS**
- mechanical_scorer_guard: **PASS**
- mechanical_replay_scorer_guard: **PASS**
- reasoning_outputs: **PASS**
- reasoning_citations: **PASS**
- reasoning_scorer_guard: **PASS**
- reasoning_replay_scorer_guard: **PASS**
- call_order_balanced: **PASS**
- all_variants_below_context_limit: **PASS**
- stability_selection: **PASS**
- stability_semantic: **PASS**
- stability_outputs: **PASS**
- stability_citations: **PASS**
- stability_scorer_guard: **PASS**
- replay: **PASS**
- live_receipts: **PASS**
- replay_receipts: **PASS**
- stability_receipts: **PASS**
- mechanical_live_recomputation: **PASS**
- mechanical_replay_recomputation: **PASS**
- expected_adversarial_count: **PASS**
- expected_no_code_count: **PASS**
