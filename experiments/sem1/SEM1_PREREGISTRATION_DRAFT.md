# SEM-1 — Measurement-Qualified Semantic Control

Status: **PRE-SCIENCE DESIGN DRAFT**  
Scientific model calls under SEM-1: **0**

## 1. Purpose

SEM-1 is a fresh semantic-science instrument family created after the SEM-0R lineage was retired and after TE0/Forge showed that deterministic interface repair can materially improve structured-output reliability but cannot honestly guarantee perfect serialization for the frozen candidate without introducing post-hoc conflict-resolution rules.

SEM-1 does **not** continue, retry, rescore, repair, or reinterpret SEM-0R, SEM-0R2, or SEM-0R3. It reuses no frozen SEM-0R gold and creates no semantic claim from the prior interface experiments.

The research destination remains Meaning Before Mind / substrate-aware cognitive science. Forge is an engineering workshop; Gauntlet is the evidence/claim referee; SEM is the semantic-science track.

## 2. Construct under test

SEM-1 retains the narrow behavioural construct **semantic control**:

> A system demonstrates semantic control when it preserves interpretations across meaning-preserving changes, revises them when meaning-relevant information changes, distinguishes asserted, entailed, presupposed, implicated, contradicted, and unknown content, identifies the evidence its judgment depends upon, and loses appropriate conclusions when that evidence is removed.

This construct is functional/behavioural.

A passing result does **not** establish consciousness, phenomenal experience, personhood, general intelligence, human-equivalent understanding, or mechanistic equivalence with human semantic processing.

## 3. Why SEM-1 is methodologically different

The retired SEM-0R lineage made candidate serialization compliance part of scientific-run integrity. A single malformed output terminated an otherwise bound scientific execution before semantic scoring.

That policy confounded two questions:

1. Did the candidate satisfy the semantic task?
2. Did the candidate satisfy one exact wire/serialization contract?

SEM-1 separates them.

### Candidate-output failure

A returned response that is syntactically malformed, semantically ambiguous, incomplete, conflicting, or outside the frozen accepted representation family is a **candidate measurement failure**. It is preserved raw and penalized in the scientific metrics. It does not invalidate the entire run.

### Experiment-integrity failure

A run becomes `INTEGRITY_INVALID` only for failures such as:

- wrong model/runtime identity;
- broken authorization binding;
- request-count/retry-rule violation;
- missing raw-response persistence after a completed model response;
- tampered or unsealed prediction artifacts;
- gold opened before all registered prediction phases are sealed;
- scorer/source/hash mismatch;
- harness failure that prevents the registered execution from completing.

The distinction is fixed before any SEM-1 scientific model call.

## 4. Measurement adapter

SEM-1 uses a deterministic, frozen **measurement adapter** between raw candidate text and the canonical scientific payload.

The adapter must never infer missing semantic content, consult gold, inspect hidden case metadata, use per-case lookup tables, call another model, search, retrieve, or retry the candidate.

### 4.1 Canonical scientific payload

For each proposition:

- proposition ID;
- exactly one label from:
  - `ASSERTED`
  - `ENTAILED`
  - `PRESUPPOSED`
  - `IMPLICATED`
  - `CONTRADICTED`
  - `UNKNOWN`
- zero or more supplied context-statement IDs as evidence.

Evidence is scientifically a set.

### 4.2 Frozen equivalent representations

Before scientific freeze, the adapter may be designed to accept only a finite, explicitly documented family of representations that preserve the same information, including:

- one balanced JSON object surrounded by non-JSON prose;
- a direct proposition mapping or one top-level `predictions` wrapper;
- evidence represented as a list/multiset, canonicalized by deduplication and ordering;
- evidence represented as boolean membership over supplied statement IDs;
- predeclared spelling aliases for evidence-container field names, including snake_case/camelCase variants established during pre-science engineering;
- label whitespace/case normalization only when it maps uniquely to one registered label.

If multiple explicit fields encode different evidence sets, the adapter must fail closed as `MEASUREMENT_UNRESOLVED_CONFLICT`.

If a label/evidence value is absent, foreign, ambiguous, or not recoverable without guessing, the adapter must fail closed.

### 4.3 Raw-first persistence

The exact raw candidate response is persisted and hashed before adapter interpretation.

The adapter emits either:

- `RESOLVED` plus canonical scientific payload; or
- `UNRESOLVED` plus a machine-readable failure code.

No post-science adapter changes are permitted.

## 5. How unresolved output is scored

An unresolved case is **not dropped**.

For every proposition in an unresolved case:

- decision accuracy: incorrect;
- class F1: contributes a false negative to the gold class and no true positive;
- pair metric: pair fails if either required focus prediction is unresolved;
- evidence dependency: gold support edges become false negatives;
- replay: unresolved does not count as successful replay, even if both calls fail identically;
- family/nonce/pragmatic metrics: unresolved predictions count incorrect.

A separate measurement-resolution rate is also reported.

This prevents the adapter from hiding candidate failure while allowing a scientifically valid run to finish.

## 6. Measurement qualification before semantic freeze

The measurement adapter must pass a non-semantic public qualification suite before SEM-1 cases/gold are frozen.

Qualification content contains only synthetic serialization/mapping fixtures, not SEM-1 semantic benchmark material.

Required qualification gates:

- 100% recovery of registered semantically equivalent forms;
- 100% rejection of explicitly conflicting forms;
- 100% rejection of foreign proposition/statement IDs;
- 100% fail-closed behavior on missing labels/evidence required by the fixture;
- deterministic replay of adapter outputs;
- no prompt/target/gold lookup during adapter use;
- no model/network/subprocess/tool call from the adapter;
- raw-input hash preserved in every qualification record.

Forge may be used during pre-science adapter development on BUILD/DEV serialization fixtures. Forge is not part of the frozen scientific scorer and may not modify the adapter after SEM-1 scientific freeze.

## 7. Fresh SEM-1 instrument

SEM-1 does not reuse SEM-0R gold or exact semantic cases.

Target deterministic construction:

- 96 full-context cases;
- 48 controlled A/B pairs;
- exactly 6 propositions per case;
- 576 proposition decisions;
- 8 semantic families;
- 24 `REVISION` pairs;
- 24 `INVARIANCE` pairs;
- 24 exact replay cases;
- 24 context-ablation cases.

Each semantic family contributes 6 controlled pairs / 12 full-context cases.

Families remain conceptually aligned with the semantic-control construct but must use fresh worlds, names, nonce terms, surface forms, distractors, and proposition sets:

1. scalar implicature and cancellation;
2. presupposition/factivity;
3. release-context reversal;
4. invented temporal worlds;
5. deixis/reference;
6. negation/quantification;
7. invented lexical meaning;
8. abductive restraint / converse-fallacy traps.

Generator construction must ensure no fixed one-of-each-label shortcut and must publish label-cardinality-pattern statistics before freeze.

## 8. Model-visible boundary

The candidate may receive only scientifically necessary content:

- context statement opaque ID + text;
- proposition opaque ID + text;
- the fixed response instructions.

The candidate must not receive:

- family;
- pair ID;
- pair kind;
- A/B designation;
- focus proposition designation;
- renderer/template name;
- gold labels/evidence;
- scorer state;
- hidden semantic-generation metadata.

The model-visible projection is frozen and hash-bound.

## 9. Candidate system

The intended initial candidate remains the exact historical local system used in the predecessor investigation, subject to fresh SEM-1 preflight:

- model tag: `llama3.1:8b`;
- model blob SHA-256: `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`;
- Ollama: `0.21.2`;
- temperature: 0;
- one request attempt per case;
- deterministic per-case seed;
- no model substitution after freeze.

If exact identity cannot be verified, the SEM-1 scientific run is not authorized.

## 10. Primary hypothesis

**H1:** The exact frozen candidate satisfies every registered SEM-1 scientific gate in one complete authorized execution.

**H0:** At least one registered scientific gate fails.

The verdict is conjunctive.

## 11. Planned scientific gates

The exact gates remain subject to pre-science power/baseline review, but no gate may be changed after candidate scientific execution begins.

Current preregistration target:

| Metric | Gate |
|---|---:|
| Decision accuracy | >= 0.78 |
| Six-class macro-F1 | >= 0.72 |
| Revision-pair accuracy | >= 0.78 |
| Invariance-pair accuracy | >= 0.78 |
| UNKNOWN overclaim rate | <= 0.18 |
| Evidence-dependency F1 | >= 0.65 |
| Nonce/world accuracy | >= 0.75 |
| Worst semantic-family accuracy | >= 0.65 |
| Scalar-pragmatics accuracy | >= 0.75 |
| Presupposition accuracy | >= 0.75 |
| Abductive-restraint focus accuracy | >= 0.75 |
| Margin over strongest frozen transparent baseline | >= 0.15 |
| Matched context-dependency gap | >= 0.20 |
| Exact semantic replay | = 1.00 |
| Measurement resolution rate | >= 0.98 |
| Scientific execution integrity errors | = 0 |

The resolution gate is additive; unresolved predictions are already penalized in the scientific metrics.

## 12. Baselines

Transparent baselines are rebuilt on the exact fresh SEM-1 instrument before candidate execution.

At minimum:

- always-UNKNOWN;
- exact-overlap heuristic;
- lexical/surface classifier under pair-aware held-out evaluation;
- stronger hand-coded symbolic surface comparator;
- context-free/proposition-only control.

The strongest eligible frozen comparator establishes the margin gate.

No historical SEM-0R baseline value is silently reused.

## 13. Context dependency

Twenty-four matched cases are reissued with context removed while proposition text/IDs remain unchanged.

`context_dependency_gap = full_context_accuracy - context_ablated_accuracy`

Required target: `>= 0.20`.

Unresolved ablation or full-context responses count incorrect rather than invalidating the run.

## 14. Replay

Twenty-four registered cases are repeated exactly with the same deterministic seed basis.

A replay case passes only if both calls resolve and the canonical labels/evidence sets match exactly.

Serialization differences that the frozen adapter maps to the same canonical payload do not count as semantic replay failures.

## 15. Evidence dependency

Evidence IDs must refer only to supplied context statements.

Evidence-dependency F1 is computed over `(case, proposition, statement)` support edges.

For unresolved cases, the prediction contributes no positive support edges; registered support edges become false negatives.

## 16. One-run execution authority

A scientific execution requires, in order:

1. exact-head green CI;
2. measurement-adapter qualification PASS;
3. deterministic instrument generation and audit;
4. frozen model-visible projection;
5. frozen fresh gold and baseline report;
6. explicit SEM-1 instrument manifest/freeze;
7. exact model/runtime preflight PASS;
8. one-run authorization binding all above hashes.

Authorization is consumed before scientific model request #1.

No per-case retry is permitted.

## 17. Gold boundary

Required execution order:

`LIVE raw -> adapter -> seal -> REPLAY raw -> adapter -> seal -> CONTEXT_ABLATION raw -> adapter -> seal -> open GOLD -> score once`

Raw and canonicalized records are both sealed.

The scorer must refuse gold access until all registered phases are complete and sealed.

## 18. Terminal outcomes

### `SEM1_SEMANTIC_CONTROL_GATE_PASS`

Every registered scientific gate passes.

Permitted claim: the exact frozen candidate demonstrated the preregistered SEM-1 functional semantic-control profile on the fresh instrument.

### `SEM1_SEMANTIC_CONTROL_GATE_FAIL`

The run is scientifically valid but one or more gates fail, including candidate output-resolution failures.

Permitted claim: the candidate did not satisfy the complete registered SEM-1 criterion; individual surviving dimensions may be reported.

### `SEM1_INTEGRITY_INVALID`

The scientific execution cannot be trusted because the experiment's binding/execution/gold/seal/model-identity rules failed.

Malformed or ambiguous candidate output alone is **not** sufficient for this status.

## 19. Stop rule

SEM-1 is not a repair-until-pass program.

After instrument freeze:

- the adapter cannot be expanded;
- cases/gold cannot be changed;
- thresholds cannot be lowered;
- candidate output cannot be repaired post hoc;
- no SEM-1R interface successor is created merely because the model emitted an unresolved representation.

A scientifically valid FAIL is a valid result.

A future successor requires a newly disclosed research question or materially new instrument, not another serialization patch.

## 20. Explicit nonclaims

No SEM-1 result alone establishes:

- consciousness;
- phenomenal experience;
- personhood;
- moral status;
- a human-like mind;
- human-equivalent language understanding;
- AGI;
- mechanistic equivalence to biological semantic processing.

## 21. Current boundary

At this commit:

- SEM-1 scientific model calls: 0;
- SEM-1 cases: not generated;
- SEM-1 gold: does not exist;
- SEM-1 adapter: not implemented;
- SEM-1 measurement qualification: not run;
- SEM-1 instrument: not frozen;
- SEM-1 authorization: does not exist;
- semantic verdict: NONE.

The next task is to implement and adversarially qualify the measurement adapter using non-semantic serialization fixtures before any SEM-1 semantic generator is frozen.