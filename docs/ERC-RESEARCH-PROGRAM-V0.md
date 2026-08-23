# ERC — Evidence Relay Compiler

Status: PRE-SCIENCE RESEARCH PROGRAM
Date: 2026-08-23

## 1. Why this branch exists

The earlier GRI/DMC/MCO lineage did not establish a transferable AI-memory architecture. That terminal negative result remains authoritative.

One narrower result survived: MCO-04 showed that a transparent deterministic compiler could reduce large incident telemetry to at most 16 auditable records while preserving 63/63 root-service localizations on held-out executions of already-seen service/fault strata. MCO-05 then showed that the same overall project did not transfer cleanly to exact-cause attribution on a disjoint workload.

ERC is a new thesis. It does not reopen the stopped architecture claim.

## 2. Cross-domain synthesis

ERC combines older ideas that normally live in separate disciplines:

1. **Protective relaying / selective isolation** — detect a disturbance locally, respect direction and zones, coordinate, and isolate the smallest responsible section rather than processing the whole grid as one undifferentiated object.
2. **Program slicing** — trace only the data/control dependencies capable of influencing an observed failure.
3. **Sufficient-state thinking** — preserve only the state needed for a specified decision, not the entire historical surface.
4. **Database provenance / witnesses** — every output must carry the exact input records that support it.
5. **Sparse-support recovery** — many engineered failures have a small responsible support set inside a much larger observation field.

No novelty claim follows from combining these ideas. The experiment must show a measurable capability that simpler existing methods do not already provide.

## 3. Core hypothesis

> In sparse fault-propagation systems, a deterministic query-conditioned dependency compiler can reduce a long observation stream to a bounded provenance-complete witness packet while preserving root-localization accuracy as system size and distractor volume increase.

This is a systems/mechanism hypothesis, not a consciousness, AGI, general causality, or world-impact claim.

## 4. What counts as a witness packet

A witness packet is a small set of source-bound records sufficient for a registered decision under the experiment's explicit dependency and scoring rules.

Every packet record must carry an opaque evidence identity, entity, observation type, event/onset time, locally recomputable statistic, dependency/path reason for inclusion, source digest, and packet-level digest. The packet may be small; the external evidence store remains complete.

## 5. ERC-0 — make it embarrassingly simple first

ERC-0 is fully synthetic and uses no language model.

### 5.1 Generator

Generate directed acyclic engineered systems at four sizes: 32, 128, 512, and 2048 nodes.

Each case contains one hidden injected fault, a directed dependency graph, baseline/post-fault observations, delayed downstream propagation, descendants that may show larger disturbances than the injected root, unrelated high-amplitude distractors, missing/weak observations, opaque node IDs, and deterministic source records/hashes.

The generator must make `largest anomaly = root` false in a substantial fraction of cases. Root placement must also be audited against a **topology-only** predictor so graph construction itself cannot leak the answer.

### 5.2 Candidate and controls

Evaluate, without tuning after seeing result rows:

1. random candidate;
2. topology-only prior (no observations);
3. largest local anomaly;
4. earliest detected anomaly;
5. simple anomalous-ancestor coverage;
6. backward time-respecting slice;
7. ERC relay score.

The ERC relay score may combine only local robust change strength, time ordering, registered dependency direction, and the fraction of anomalous downstream evidence coherently covered. It may not use the hidden root label.

### 5.3 Simplicity precedence

Complexity receives no credit merely for tying a simpler rule.

Outcome precedence:

1. `ERC0_INTEGRITY_INVALID` — generator/scorer/provenance/replay failure.
2. `ERC0_CONSTRUCTION_SHORTCUT` — topology-only prediction is strong enough to make root placement itself a meaningful shortcut.
3. `ERC0_NONTOPOLOGICAL_SUFFICIENT` — a non-topological observation control is within 0.02 top-1 of the best valid method while clearing quality gates.
4. `ERC0_SIMPLE_SLICE_SUFFICIENT` — the simple topology/slice control is within 0.02 top-1 of ERC while clearing quality gates.
5. `ERC0_RELAY_ADVANCE` — ERC clears all gates and beats the best simpler valid control by at least 0.05 top-1.
6. `ERC0_SYNTHETIC_FAIL` — no bounded transparent method clears registered quality gates.

The simpler surviving mechanism becomes the next candidate. The project does not preserve complexity for branding reasons.

### 5.4 ERC-0 gates

Before any result is observed, require:

- overall root top-1 >= 0.85 for an advancing mechanism;
- top-1 >= 0.75 at every registered graph size;
- root top-3 >= 0.95 overall;
- packet capacity <= 16 records in 100% of cases;
- provenance recomputation = 1.00;
- exact replay = 1.00;
- accuracy loss from 32 to 2048 nodes <= 0.10;
- topology-only top-1 < 0.35, otherwise construction shortcut;
- best non-topological observation-control margin >= 0.15 for a topology-dependent claim;
- ERC-vs-simple-slice margin >= 0.05 for ERC-specific mechanism credit.

If the simple slice clears quality gates and is within 0.02 of ERC, credit the slice, not ERC.

## 6. Scale ladder

### ERC-0: synthetic graph mechanics

Question: does any bounded transparent mechanism survive scale and distractors? No LLM, natural language, or public benchmark labels.

### ERC-1: clean-room MCO-04 reproduction

Reimplement the MCO-04 direct compiler from its frozen contract without importing its implementation. Require fresh checkout, pinned RCAEval bytes, independent code, scorer isolation, reproduced source hashes, and either the 63-case result or an explicit discrepancy report. The target is reproducibility, not a new claim.

### ERC-2: cross-domain transfer

Freeze one generic mechanism before running three domains:

1. microservice telemetry — RCAEval;
2. chemical/process telemetry — Tennessee Eastman process data;
3. electrical network faults — a standard network such as IEEE 33-bus with fault simulations generated through an independently maintained power-systems package.

Domain adapters may map raw measurements into the generic observation schema. Ranking/packet logic may not be retuned per domain. Necessary domain-specific rules are disclosed and lose generic-mechanism credit.

### ERC-3: missing topology and graph error

Attack with 5%, 10%, 20%, and 40% missing edges, spurious edges, timestamp jitter, sensor dropout, hidden intermediate nodes, and schema changes. Measure graceful degradation.

### ERC-4: multiple simultaneous faults

Remove single-fault sparsity. Require explicit multi-root support recovery, bounded packets, and no collapse into one convenient root.

### ERC-5: prospective hidden workload

A third party or isolated operator freezes unseen incidents before execution. Development receives no labels. Only this stage can materially upgrade a transfer/generalization claim.

## 7. Hard controls inherited from other disciplines

Later stages compare against serious controls: dynamic/backward slicing, spectrum/statistical fault localization, BARO and RCAEval causal/graph/multi-source baselines, full-history/oracle bounds, exact structured lookup where structure makes the answer trivial, minimal-witness/provenance methods where the task reduces to database derivation, and domain-standard chemical-process and power-system diagnosis baselines.

If an established transparent method matches ERC, that is useful evidence and ERC receives no mechanism novelty credit.

## 8. Compression is not enough

Always report decision accuracy, packet size, raw-to-packet ratio, support/witness recall, provenance correctness, runtime/memory, error by size/path/distractor load, and the strongest simpler control. Never report compression alone as an intelligence or architecture advance.

## 9. Counterfactual deletion test

For each retained packet record, remove it and recompute the registered decision. Classify it as necessary, redundant-but-corroborating, or irrelevant. A mechanism with many irrelevant records fails mechanism-credit ablation even if packet size is below 16.

## 10. Research boundary

ERC does not currently establish true causal identification from arbitrary observational data; a novel theory of sufficient statistics, provenance, or protective relaying; general intelligence or semantic understanding; superiority over established RCA methods; or production/economic value.

The first question is smaller:

> Is there a simple, reproducible, bounded evidence-selection mechanism hiding inside the earlier MCO results that survives scale, serious nulls, and cross-domain transfer?

If no, stop. If yes, keep simplifying until the smallest surviving mechanism is exposed.
