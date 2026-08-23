# MCO-03 — RELATION BOUNDARY / STATE COMPILER

## Claim under test

A frozen, single-record constrained language normalizer can repair MCO-02's relation boundary and produce exact bounded state packets that retain quality against equally informed transparent compilation and strong dense/hybrid RAG controls.

## Check

Self-verified preregistered experiment on the unchanged MCO-02 population: 8 histories, 32,200 records, 64 queries, frozen Llama 3.1 8B extraction/reasoning, frozen EmbeddingGemma dense retrieval, deterministic transparent compilation, live stability repeats, and frozen-response replay.

| Component | Relation/answer | Critical/provenance | Model calls | Expensive units |
|---|---:|---:|---:|---:|
| learned single-record extraction | 100.00% | 100.00% | 32,200 | 5,642,294 |
| transparent compiler | 100.00% | n/a | 0 | 0 |
| learned exact packet | 100.00% | 100.00% | 0 packet-selection calls | 0 packet-selection units |
| frozen model over learned packet | 100.00% | 53.12% | 1.00/query | 758.7/query |
| dense_rag | 4.69% | 0.00% | 1 reasoning/query | 1577.2/query |
| entity_hybrid_rag | 70.31% | 18.75% | 1 reasoning/query | 993.9/query |
| hybrid_rag | 3.12% | 0.00% | 1 reasoning/query | 1605.2/query |

## Verdict — FAIL

`MCO_03_TRANSPARENT_COMPILER_DOMINATES`

## Criteria

- integrity_pass: **PASS**
- learned_extraction_quality: **PASS**
- learned_packet_quality: **PASS**
- frozen_downstream_quality: **FAIL**
- stability_pass: **PASS**
- state_compiler_quality: **FAIL**
- transparent_compiler_dominates: **PASS**
- hybrid_rag_dominates: **FAIL**

## Assumption register

- Verified here: relation normalization, exact packet selection, bounded contexts, local token/call accounting, semantic/raw stability, and deterministic replay on the frozen synthetic renderer.
- Checkable but unchecked here: arbitrary real documents, OCR, entity ambiguity, mutable schemas, access control, production concurrency, user demand, and deployment economics.
- The transparent compiler knows the renderer's finite language templates but receives no oracle labels, queries, or answers. Its result cannot be generalized to open language.
- Embedding retrieval uses the same complete raw record store and 16-record model-visible budget; entity-aware RAG additionally uses deterministic subject/entity parsing available in the public text.
- Societal impact remains externally contingent and unfalsifiable in this experiment.

## Credit assignment

Learned normalization receives credit only if its frozen quality gates pass. Exact packet selection receives separate credit from the model's ability to copy provenance. If transparent compilation matches quality with zero model calls, it receives architecture credit for this synthetic family; learned retention and DMC receive none.

## Verification gap

No independent verifier was available, so the result is self-verified. Frozen replay checks the harness, not independent replication. The next authorized test, if any, must use real incident evidence and externally checkable outcomes.

## Stop/continue

STOP learned extraction work on this synthetic family. CONTINUE only with MCO-04, a real software-incident state-compiler product proof using deterministic or constrained normalization, exact provenance, and a strong retrieval control.

## Is this going to change the world?

**NOT_ESTABLISHED.** A controlled synthetic mechanism—even if valid—does not establish novelty, customer demand, independent replication, production reliability, adoption, or long-horizon societal impact.

## Maturity status

`MATURE_CONTROLLED_SYNTHETIC_BOUNDARY_TEST; EARLY_UNVALIDATED_REAL_WORLD_PRODUCT; WORLD_IMPACT_CLAIM_NOT_MATURE`

## Verification status

`SELF_VERIFIED`; integrity: `PASS`
