# MCO-02 — LANGUAGE / INFERENCE BOUNDARY

## Claim under test

Complete externally stored natural-language history can preserve equivalent task quality with bounded model-visible state and materially lower total expensive inference than context-heavy or conventional retrieval after ingestion is amortized.

MCO-02 attacks the largest surviving MCO-01 assumption: that the world has already been converted into perfect records and exact indexes. It is a language-boundary and inference-accounting experiment, not a learned-memory experiment.

## Frozen population

The frozen MCO-01 semantic generator produces two seeds at 100, 1,000, 5,000, and 10,000 events. Each of the eight histories has eight queries, with two queries at each dependency length from two through five. This yields 32,200 semantic event records and 64 questions.

The renderer must preserve ground truth while introducing at least four frozen phrasings per semantic relation, local pronoun/coreference constructions, inverse-looking but semantically unambiguous prose, corrections, supersession, renames, source-ranked contradictions, irrelevant narrative, and temporal wording. Record and entity IDs remain opaque and explicit because provenance must be scoreable. Rendered text may not expose canonical relation names, utility labels, query IDs, criticality, or answers.

## Model and tokenizer fairness

Every live language extraction, summary, acquisition, and reasoning call uses the same frozen local `llama3.1:8b` Ollama model, model blob, tokenizer, temperature, and seed. Extraction uses an 8,192-token batching context. Bounded query systems use at most 8,192 tokens and 16 visible event records. Full context may use up to the frozen deployed 32,768-token limit. The model's native 131,072-token metadata is reported separately; the deployed limit is a hardware-bounded experimental configuration, not a claim about the architecture's theoretical maximum.

Rolling-summary ingestion may use a 16,384-token context while compressing 256-record chunks. This ingestion workspace is charged in full but is not model-visible query state.

The selected model passed a 12-item benchmark-independent engineering smoke before corpus generation. Those model-selection calls are not scientific observations and must not be included in MCO-02 scores.

An explicitly unscored 100-record integration smoke then exposed two interface defects before corpus materialization or scientific inference: oversized 96-record relation batches produced malformed outputs, and the query prompt did not make signed-temperature comparison sufficiently explicit. Engineering amendment `MCO02-ENG-01` reduces classification batches to 12, passes only the deterministically isolated semantic sentence to the relation classifier, and clarifies the signed-integer/output protocol. The semantic population, renderer, systems, model, capacities, thresholds, and verdict precedence are unchanged. The failed smoke and amendment receipt remain preserved under `artifacts/mco02/engineering` and `experiments/mco02`.

A second explicitly unscored smoke showed that free-form label lists still produced 88% exact extraction and that a free-form model-only `NEED` protocol could hallucinate an answer before retrieving any record. Engineering amendment `MCO02-ENG-02` uses schema-constrained ordered JSON for relation labels, restores MCO-01's transparent indexed bundle controller while leaving the model responsible for selecting each winning nonterminal record and next entity, replaces delimiter-sensitive final answers with one evidence-grounded JSON interface shared by all six systems, and derives the inspection flag through one identical transparent integer comparison for all systems. A pre-amendment schema probe reached 98% exact extraction on the same engineering fixture. This probe is engineering evidence only; it cannot contribute to scientific scores. Population, language, model, capacities, thresholds, and verdict precedence remain unchanged.

## Shared extraction boundary

Structured exact planning and iterative `NEED(...)` receive byte-identical extracted records from one shared pipeline. The pipeline uses deterministic scaffolding for explicit record IDs, entity IDs, source labels, event times, numeric values, and explicit update references. The frozen model classifies the semantic relation expressed by each natural-language record from its deterministically isolated semantic sentence, without oracle fields, queries, or answers. This hybrid boundary is deliberate and must be credited narrowly: it tests language normalization, not unconstrained open-domain information extraction.

Frozen extraction batches contain at most 12 records and are structurally valid only when their schema-constrained JSON contains one allowed relation label per input record, in order. A malformed batch may be recursively split without consulting ground truth. A semantically wrong but structurally valid prediction may not be retried. Every failed and successful call counts toward ingestion.

Extraction precision and recall are exact-record measures against the hidden semantic records. Relation classification is also reported separately. Indexing integrity is checked after extraction so indexing failures cannot be confused with extraction failures.

## Systems

| System | Persistent representation | Model-visible history |
|---|---|---:|
| Full context | raw language | all records while ≤32,768 tokens |
| Recent window | raw language | final 16 records |
| Rolling summary | model-selected summary plus recent language | 8 + 8 records |
| Conventional RAG | raw language plus frozen TF-IDF word/character index | top 16 records |
| Structured exact planner | shared extracted structured store | winning path, ≤16 records |
| Iterative `NEED(...)` | same extracted store | acquired bundles, ≤16 records |

Full context overflows are recorded as `FULL_CONTEXT_INFEASIBLE` and excluded from accuracy denominators. Conventional RAG is one-shot: it cannot reformulate after reading its first top-16 result. Iterative acquisition inherits the transparent relation precedence and indexed bundle retrieval from frozen MCO-01; at each nonterminal bundle, the model must select the winning visible record and its object entity through a schema-constrained `NEED` interface. The controller validates and executes that request but does not substitute the winning candidate. Structured exact planning performs full transparent graph traversal outside the model and exposes only the resolved winning path.

All six systems use the same evidence-grounded JSON answer schema. Allowed terminal entities, threshold values, and provenance IDs come only from records already visible to that model call; the model must select the terminal/threshold and ordered path. All systems then use the same post-response rule for inspection: the harness computes `deployment_temperature < threshold`. This removes delimiter and signed-arithmetic variance without granting any system evidence that its retriever did not expose.

## Cost boundary

Costs are separated into ingestion, query, and total/amortized buckets.

Ingestion includes extraction or summary model calls, actual model-reported input/output tokens, index construction, persistent writes, and wall time. Query includes retrieval/index operations, every acquisition and reasoning call, actual tokens, and wall time. Total cost is reported for 1, 2, 8, 32, and 128 queries per history.

The primary hardware-independent inference measure is:

```text
expensive token units = input tokens + 4 × output tokens
```

Sensitivity at output weights 1 and 10 is also reported. Because inference is local, billed API cost is zero and no fabricated USD estimate is allowed. Local wall time and call counts remain descriptive measurements. Break-even comparisons are valid only between systems whose answer accuracy differs by no more than five percentage points.

## Mechanical failure attribution

Each wrong answer receives exactly one earliest-cause label:

1. `LANGUAGE_EXTRACTION_FAILURE` when an expected critical record was mistranslated before indexing.
2. `INDEXING_FAILURE` when a correctly extracted critical record is absent or corrupted in the index.
3. `RETRIEVAL_FAILURE` when a non-iterative retriever fails to expose complete critical evidence.
4. `ACQUISITION_PLANNING_FAILURE` when iterative model output requests an invalid or wrong next entity or stops too early.
5. `REASONING_FAILURE` when complete correct evidence is visible but the model's answer is wrong.
6. `PROVENANCE_FAILURE` when the semantic answer is correct but the required record-ID path is wrong.

No wrong answer may remain unclassified.

## Integrity gates

Before a scientific verdict, the harness must establish:

1. MCO-01 terminal and generator identities match frozen hashes.
2. Exact seed/load/query/event counts and semantic reconstruction pass.
3. Rendering preserves every semantic value and reference while exposing no forbidden labels.
4. The two structured systems consume the same extraction artifact hash.
5. Actual model identity, tokenizer metadata, options, and response accounting are recorded for every call.
6. All bounded systems stay within 16 visible records and 8,192 reported prompt tokens.
7. Full-context infeasibility is excluded, not scored as failure.
8. Every metric denominator and failure label reconciles to the frozen population.
9. A stratified 10% live response repeat measures deterministic stability.
10. Two complete downstream replays from frozen model responses are byte-identical after declared wall-clock exclusions.

Any failed integrity gate produces `MCO_02_ACCOUNTING_INVALID`.

At least 95% of stratified repeated live responses must be byte-identical. Token counts are reported separately; response-content stability is the frozen integrity threshold.

## Mechanical verdict

Verdicts follow `MCO02_CONFIG.json` precedence.

- `MCO_02_LANGUAGE_TRANSFER_FAILS`: extraction or structured answer quality misses the frozen minimum.
- `MCO_02_RAG_DOMINATES`: quality-equivalent conventional RAG is materially cheaper through 128 queries.
- `MCO_02_EXTRACTION_COST_DOMINATES`: a quality-equivalent nonstructured baseline remains at least 25% cheaper at 128 queries because extraction has not amortized.
- `MCO_02_STRUCTURED_PLANNER_DOMINATES`: language-to-structure works, but exact transparent planning matches iterative quality with materially fewer query calls or expensive-token units.
- `MCO_02_LANGUAGE_BOUNDARY_ADVANCES`: bounded external structure survives language and materially lowers total expensive inference after amortization without a simpler baseline dominating.
- `MCO_02_INCONCLUSIVE`: all accounting is valid but no terminal scientific branch meets its threshold.

## Credit boundary and world-impact question

A pass can credit only the frozen hybrid language normalization, complete external structured storage, and the measured acquisition/planning policy. It cannot establish open-domain extraction, production economics, scientific novelty, adoption, independent replication, or societal impact.

“This project will change the world” is not falsifiable in this environment and cannot become verified from MCO-02. The strongest honest disposition is `NOT_ESTABLISHED`; changing that would require independent replication, real workloads and users, production reliability/security evidence, and longitudinal adoption evidence.

## Stop rule

After the first valid terminal MCO-02 verdict, stop architecture modification. Preserve all raw model responses and failure traces. Continue only with the smallest experiment named by the terminal branch; do not introduce learning, latent memory, multi-agent machinery, or new models to rescue a failure.
