# MCO-05 — DISJOINT CHANGE-ATTRIBUTION STATE-COMPILER GATE

## Claim under test

Without seeing any RootCauseBench scenario during development, can a generic
transparent state compiler reduce complete incident telemetry and change
context to at most 16 auditable records so that a frozen reasoner identifies
the causal commit more accurately than deterministic RCA, hybrid retrieval,
and maximum-safe-context controls?

This is a disjoint-workload transfer claim. It is not a claim of general AI
memory, organic-production validation, product-market fit, or world impact.

## Benchmark boundary

Use all 36 scenarios at pinned RootCauseBench commit
`0c3c476e4627978dc54b5c047fd488d40561b4e5` as scientific-only cases. There
are zero benchmark engineering cases. Code, configuration, prompts, thresholds,
capacities, models, outcome logic, and tests freeze before any scenario file is
cloned locally.

The benchmark is Apache-2.0. It contains 28 code-cause and eight no-code-cause
incidents, including 12 adversarial cases. Most cases are fictional
reconstructions of representative production incident classes; a few are fault
injections. This changes task structure from RCAEval service localization to
commit attribution, but it is not an organic production pilot.

RootCauseBench is public and its documentation describes scenario mechanisms.
This experiment therefore claims executable isolation, not experimenter
blindness. Source scenario names, difficulty tags, oracle files, culprit labels,
and decoy labels are scorer-only. Visible files receive opaque IDs. A static
literal audit and a runtime read guard must pass.

## Frozen state compiler

The evidence layer preserves hashes and bytes for the visible alert, instruction,
logs, metrics, traces, clustered patterns, commits, deploys, and feature flags.
The compiler creates deterministic, provenance-linked documents:

1. the alert and sanitized task instruction;
2. robust metric summaries with data-derived change points;
3. aggregated log signatures, trace summaries, and supplied patterns;
4. deployed-commit records linking commit metadata, files, diffs, deployment
   service, and deployment time; and
5. flag/deploy events.

Candidate ranking may use only visible timing, service linkage, anomaly scores,
and lexical overlap between symptoms and commit content. It receives no oracle
labels. The packet contains one alert record, at most five telemetry records,
and at most ten candidate-commit records, never exceeding 16 records or 15,000
UTF-8 complete user-prompt bytes. The complete visible evidence remains outside
the model.

Candidate coverage is scored separately from model reasoning. A wrong answer is
classified as selection failure when the true commit was absent from the packet,
reasoning failure when it was present, abstention failure for a no-code case, or
provenance/output failure where mechanically applicable.

## Controls

Run the official-policy equivalents of latest commit, always-none, latest
deploy, earliest deploy, alert-service deploy, and scripted RCA. Also run:

- lexical+dense hybrid RAG over the same compiled visible documents, top-k 16;
- a deterministic maximum-safe-context prefix over the same documents, capped
  at 15,000 UTF-8 complete user-prompt bytes and receipt-verified below 8,192
  tokens; and
- the frozen reasoner over the compiler packet.

All reasoning variants use the same Llama 3.1 8B model, output schema, seed,
context limit, and maximum generation. Hybrid retrieval uses the frozen
EmbeddingGemma model. Retrieval preprocessing, embedding ingestion, query
embedding, model tokens, calls, wall time, and replay are accounted separately.
Cached replay is never credited as fresh inference.

## Gates

Integrity requires exact source identity, opacity, provenance recomputation,
capacity compliance, valid/cited outputs, model identities, scorer isolation,
fresh semantic stability of at least 95%, and byte-seal-identical replay.

Transfer requires candidate recall at least 90%, packet exact-commit accuracy at
least 50%, Wilson 95% lower bound at least 35%, no-code accuracy at least 50%,
and adversarial accuracy at least 25%. Architecture advantage additionally
requires at least five percentage points over the strongest equally informed
reasoned control.

## Terminal outcomes

- `MCO_05_BENCHMARK_INVALID`: isolation, provenance, accounting, stability, or
  replay fails.
- `MCO_05_DISJOINT_COMPILER_TRANSFER_FAILURE`: the bounded selector fails
  candidate recall or packet mechanics.
- `MCO_05_DISJOINT_REASONING_FAILURE`: selection transfers but bounded reasoning
  misses frozen absolute quality gates.
- `MCO_05_CONVENTIONAL_RETRIEVAL_DOMINATES`: an equally informed conventional
  control is equivalent or better.
- `MCO_05_DISJOINT_BOUNDED_INFERENCE_ADVANCE`: all absolute gates pass and the
  packet materially beats every reasoned control.

## Stop rule

Any failure or conventional-dominance label stops the state-compiler product
claim on this evidence. An advance authorizes only an independently operated,
prospective incident pilot. No public synthetic/reconstructed benchmark result
can establish that the project will change the world.

Historical accounting remains explicit: DMC used 10,880 reconstructed optimizer
steps and remains `TRAINING_COST_UNKNOWN`. Zero MCO-05 optimizer steps do not
make pretrained models free; their training cost is unknown and nonzero.
