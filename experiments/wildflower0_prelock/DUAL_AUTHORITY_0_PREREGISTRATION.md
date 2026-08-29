# WILDFLOWER Dual-Authority-0 preregistration

Status: **DESIGN FROZEN BEFORE ANY SCORED EXECUTION**

This experiment is the first WILDFLOWER unit that integrates the already-replicated predictive-authority mechanism with a reversible machine-native epistemic state and an independent world-witness boundary in one sequential learner.

It is not a new claim about AGI, consciousness, language, universal world modeling, or optimal machine representation. It does not reopen the historical PRIMITIVE experiments as fresh evidence.

## Question

Can a world-first developmental learner keep the previously replicated predictive-authority safety/performance behavior while preventing model-generated false conclusions from becoming durable knowledge, using:

1. a distinct predictive authority that decides whether learned dynamics may override a transparent velocity null;
2. provisional machine-native claims;
3. explicit support/dependency structure;
4. independent direct world observations;
5. reversible rollback and grounded recomputation?

The two authorities are deliberately separate. No single scalar is allowed to decide both prediction control and durable epistemic commitment.

## Hard language boundary

Natural language is forbidden from the cognitive path.

Learner/cognitive inputs may contain only:

- numeric object-state arrays derived from sensor pixels;
- raw machine action IDs already used by Nursery-1;
- integer machine-native packets;
- integer support/dependency references;
- numeric predictive-authority values derived from learner-visible innovation.

Forbidden cognitive inputs include:

- tokens or tokenizer output;
- transcripts;
- text labels;
- LLM output;
- CLIP/Whisper/RAG embeddings or routing;
- hidden Nursery-1 mode;
- evaluator-only collision, boundary, or rule-event flags.

Human-readable names in source code, test names, documentation, and final reports are evaluator/engineering conveniences only. Runtime packet payloads are integer fields.

## Historical constraints imported without rerunning old experiments

The design incorporates only constraints already recovered from the historical lineage:

- predictive and epistemic authority must remain separate;
- generated conclusions must remain reversible through support/dependency state;
- internal coherence alone is insufficient for durable commitment;
- independent world evidence must be able to contradict a model-generated claim;
- unsupported descendants must be retractable;
- alternate surviving support must preserve a still-supported claim;
- observable gates are frozen before execution.

Historical PRIMITIVE results are background evidence only. Historical ENCODING results are used only to choose a conservative packet transport shape; encoding is not a scored scientific variable in this experiment.

## Frozen predictive-authority source

Dual-Authority-0 reuses the previously replicated predictive-authority implementation and constants without modification:

- `probe_innovation_model.py` SHA-256  
  `97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1`
- `qualify_authority190.py` SHA-256  
  `13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e`
- innovation threshold: `0.30` cells
- transition width: `0.30` cells
- rollout decay: `0.998`
- burn history: `12`

No change to the predictive model, authority formula, threshold, width, or decay is authorized by this experiment.

## Fresh developmental set

The scored run is one-shot.

- model seed: `310`
- balanced training episodes: `2` per hidden mode
- balanced ordinary predictive test episodes: `2` per hidden mode
- balanced epistemic challenge episodes: `1` per hidden mode
- training selector root: `MODEL_SEED + 9000`, start `600000`
- ordinary test selector root: `MODEL_SEED + 19000`, start `650000`
- challenge selector root: `MODEL_SEED + 29000`, start `700000`
- training episode length: `420`
- ordinary evaluation length: `520`
- epistemic challenge length: `260`
- training steps per episode: `80`

Exact episode IDs are generated only inside the separately authorized scored run.

The epistemic challenge uses Nursery-1's already-existing deterministic `surprise=True` world perturbations. This is preregistered here before scoring. Surprise/event metadata remain unavailable to the cognitive path.

## Sequential cognitive cycle

For each eligible challenge transition:

1. the frozen predictive-authority mechanism produces a one-step numeric state proposal;
2. that proposal is converted to integer coordinate claims with status `PROVISIONAL`;
3. machine-native pair relations and a second-generation parity claim are derived from those provisional parents;
4. no prediction-derived claim may become durable from internal coherence alone;
5. the next direct sensor-derived coordinate observation enters through the world-witness boundary;
6. matching prediction support is retired and replaced by the world-rooted support;
7. conflicting prediction support is retired;
8. support/dependency status is recomputed;
9. unsupported descendants become revoked automatically;
10. correct derived claims are recomputed from committed coordinate parents;
11. durable memory may contain only claims with an active support path rooted in world observation.

Evaluator truth for relation/parity scoring is calculated outside the cognitive store. Relation/parity truth is **not** injected as a direct witness.

That distinction is essential: the experiment must demonstrate dependency rollback, not merely correct every derived slot by handing the answer to the store.

## Machine-native packet

Every packet has exactly six integer fields:

`STABLE_REFERENCE, ACT, SUBJECT, RELATION, OBJECT, VALUE`

The packet contract and encoding boundary are frozen separately in `DUAL_AUTHORITY_0_PACKET_CONTRACT.md`.

## Preregistered controls

All controls see the same generated packet opportunities.

### Predictive controls

- transparent velocity null;
- frozen learned model without external predictive authority.

These are inherited from the replicated authority instrument and remain reportable on the fresh set.

### Epistemic controls

`DIRECT_COMMIT`

Prediction-derived coordinate and derived packets become durable immediately. No rollback is available.

`CONFIDENCE_COMMIT`

Prediction-derived packets become durable whenever frozen predictive authority is at least `0.50`. This intentionally tests the tempting but invalid idea that predictive authority can double as epistemic truth confidence.

`DAG_NO_WITNESS`

The dependency graph exists, but no independent world observation is admitted. Prediction-derived claims may remain provisional but cannot acquire durable world-rooted status.

`WITNESS_NO_DAG`

Direct coordinate witness is available, but previously emitted derived claims have no dependency links to corrected parents. Stale descendants therefore cannot be recursively located through provenance.

No control may be tuned after seeing the fresh result.

## Predictive-authority preservation gates

All six remain conjunctive on the fresh ordinary set:

1. worst h1 ratio versus velocity null `<= 1.10`
2. worst h8 ratio `<= 1.00`
3. mean h8 ratio `<= 0.90`
4. worst h32 ratio `<= 1.00`
5. mean h32 ratio `<= 0.85`
6. event-window mean h8 ratio `<= 0.90`

Failure here is classified as `PREDICTIVE_AUTHORITY_FAILED`; the epistemic layer cannot rescue it.

## Epistemic challenge adequacy gates

The challenge must produce enough natural contradiction opportunities before a positive mechanism claim is possible:

- total prediction/truth contradictions: at least `30`
- derived relation/parity contradictions: at least `10`
- alternate-support preservation opportunities: at least `5`

If any of these are absent, the terminal verdict is `INSUFFICIENT_CHALLENGE`. The set is spent; no same-set tuning or seed replacement is allowed.

## Epistemic authority gates

Given an adequate challenge:

1. wrong prediction-derived claims committed before witness: exactly `0`
2. rollback recall over contradicted predicted claims: exactly `1.0`
3. false durable claims after world witness + grounded recomputation: exactly `0`
4. durable truth coverage across scored coordinate/relation/parity slots: at least `0.99`
5. alternate-support preservation rate: exactly `1.0`
6. numeric transition-ledger replay: exact for every challenge episode
7. active claim count never exceeds `8192`

A miss is `EPISTEMIC_AUTHORITY_FAILED`.

## Mechanism-credit gates

Passing the candidate gates is not sufficient. The integrated mechanism receives credit only if:

1. Dual Authority leaves zero false durable claims while `DIRECT_COMMIT` leaves at least one;
2. Dual Authority achieves exact rollback while `WITNESS_NO_DAG` leaves at least one stale derived descendant;
3. Dual Authority achieves at least `0.99` durable coverage while `DAG_NO_WITNESS` remains at zero durable coverage.

`CONFIDENCE_COMMIT` is preregistered and reported, but it is not required to fail. If it happens to make no false durable commitment on the fresh set, that fact is preserved rather than retuning its threshold.

If candidate gates pass but mechanism-credit gates do not, the terminal verdict is `MECHANISM_UNRESOLVED`.

## Terminal verdicts

Exactly one of:

- `PREDICTIVE_AUTHORITY_FAILED`
- `INSUFFICIENT_CHALLENGE`
- `EPISTEMIC_AUTHORITY_FAILED`
- `MECHANISM_UNRESOLVED`
- `DUAL_AUTHORITY_DEMONSTRATED_WITHIN_TESTED_SCOPE`

The positive verdict means only that this integrated two-boundary mechanism survived the frozen Nursery-1 developmental instrument.

## Replay, provenance, and one-shot execution

The scored runner must execute twice from identical frozen bytes and produce byte-identical JSON.

The scored workflow must verify:

- the authorization commit's parent SHA;
- the freeze-manifest digest;
- all frozen source SHA-256 values;
- the byte-locked predictive-authority sources;
- regression tests for hidden-mode leakage;
- regression tests for predictive-authority bypass;
- regression tests for epistemic-authority bypass;
- packet roundtrip determinism;
- transition-ledger replay;
- absence of forbidden language-model dependencies.

A scientific FAIL is a valid completed run and must still be uploaded as evidence.

## Authorization boundary

This preregistration, implementation, tests, workflow, and freeze manifest may be committed and exercised in **preflight only**.

No scored Dual-Authority-0 run is authorized until:

1. hosted preflight is green;
2. the freeze manifest is committed;
3. an explicit `DUAL_AUTHORITY_0_AUTHORIZATION.json` is added in a later, separate commit.

PR #29 remains draft. A positive result would not itself authorize merging or freezing the overall WILDFLOWER architecture.
