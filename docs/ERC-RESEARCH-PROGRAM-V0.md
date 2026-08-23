# ERC — Evidence Relay Compiler

Status: PRE-SCIENCE RESEARCH PROGRAM
Date: 2026-08-23

## 1. Why this branch exists

The earlier GRI/DMC/MCO lineage did not establish a transferable AI-memory architecture. That terminal negative result remains authoritative.

One narrower result survived: MCO-04 showed that a transparent deterministic compiler could reduce large incident telemetry to at most 16 auditable records while preserving 63/63 root-service localizations on held-out executions of already-seen service/fault strata. MCO-05 then showed that the same overall project did not transfer cleanly to exact-cause attribution on a disjoint workload.

ERC is a new thesis. It does not reopen the stopped architecture claim.

## 2. Cross-domain synthesis

ERC combines four older ideas that normally live in separate disciplines:

1. **Protective relaying / selective isolation** — detect a disturbance locally, respect direction and zones, coordinate, and isolate the smallest responsible section rather than processing the whole grid as one undifferentiated object.
2. **Program slicing** — trace only the data/control dependencies capable of influencing an observed failure.
3. **Sufficient-state thinking** — preserve only the state needed for a specified decision, not the entire historical surface.
4. **Database provenance / witnesses** — every output must carry the exact input records that support it.

Sparse-support recovery is a fifth analogy: in many engineered failures, only a small subset of components is responsible for a very large observation field.

No novelty claim follows from combining these ideas. The experiment must show a measurable capability that simpler existing methods do not already provide.

## 3. Core hypothesis

> In sparse fault-propagation systems, a deterministic query-conditioned dependency compiler can reduce a long observation stream to a bounded provenance-complete witness packet while preserving root-localization accuracy as system size and distractor volume increase.

This is a systems/mechanism hypothesis, not a consciousness, AGI, general causality, or world-impact claim.

## 4. What counts as a witness packet

A witness packet is a small set of source-bound records that is sufficient for a registered decision under the experiment's explicit dependency and scoring rules.

Every packet record must contain:

- opaque source/evidence ID;
- component/entity ID;
- observation type;
- event/onset time;
- locally recomputable anomaly statistic;
- dependency/path relation used to include it;
- source digest or deterministic source identity;
- packet-level digest.

The packet may be small. The external evidence store remains complete.

## 5. ERC-0 — make it embarrassingly simple first

ERC-0 is fully synthetic and uses no language model.

### 5.1 Generator

Generate directed acyclic engineered systems at four sizes:

- 32 nodes;
- 128 nodes;
- 512 nodes;
- 2048 nodes.

Each case contains:

- one hidden injected fault;
- a directed dependency graph;
- baseline and post-fault observations at every node;
- delayed downstream propagation;
- descendants that may show larger disturbances than the injected root;
- unrelated high-amplitude distractor anomalies;
- missing/weak observations;
- opaque node IDs;
- deterministic source records and hashes.

The generator must make the trivial `largest anomaly = root` shortcut false in a substantial fraction of cases.

### 5.2 Candidate and controls

Evaluate, without tuning after seeing scientific cases:

1. largest local anomaly;
2. earliest detected anomaly;
3. random candidate;
4. simple anomalous-ancestor coverage;
5. backward time-respecting slice;
6. ERC relay score.

The ERC relay score may combine only:

- local robust change strength;
- time ordering;
- registered dependency direction;
- fraction of anomalous downstream evidence coherently covered.

It may not use the hidden root label.

### 5.3 Simplicity precedence

Complexity receives no credit merely for tying a simpler rule.

Outcome precedence:

1. `ERC0_INTEGRITY_INVALID` — generator/scorer/provenance/replay failure.
2. `ERC0_NONTOPOLOGICAL_SUFFICIENT` — a non-topological transparent control is within 0.02 top-1 of the best valid method while clearing the quality gates.
3. `ERC0_SIMPLE_SLICE_SUFFICIENT` — the simple topology/slice control is within 0.02 top-1 of ERC while clearing the quality gates.
4. `ERC0_RELAY_ADVANCE` — ERC clears all gates and beats the best simpler valid control by at least 0.05 top-1.
5. `ERC0_SYNTHETIC_FAIL` — no bounded transparent method clears the registered quality gates.

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
- best non-topological-control margin >= 0.15 for a topology-dependent claim;
- ERC-vs-simple-slice margin >= 0.05 for ERC-specific mechanism credit.

If the simple slice clears the quality gates and is within 0.02 of ERC, credit the slice, not ERC.

## 6. Scale ladder

Do not jump directly to the hardest workload.

### ERC-0: synthetic graph mechanics

Question: does any bounded transparent mechanism survive scale and distractors?

No LLM. No natural language. No public benchmark labels.

### ERC-1: clean-room MCO-04 reproduction

Reimplement the MCO-04 direct compiler from its frozen contract without importing its implementation.

Required:

- fresh checkout;
- pinned RCAEval bytes;
- independent implementation;
- scorer isolation;
- reproduced source hashes;
- reproduced 63-case scientific result or an explicit discrepancy report.

The target is reproducibility, not a new claim.

### ERC-2: cross-domain transfer

Freeze one generic mechanism before running three domains:

1. microservice telemetry — RCAEval;
2. chemical/process telemetry — Tennessee Eastman process data;
3. electrical network faults — a standard test network such as IEEE 33-bus, with fault calculations/simulations generated from an independently maintained power-systems package.

Domain adapters may map raw measurements into the registered generic observation schema. The ranking/packet mechanism may not be retuned per domain.

A domain-specific rule that is necessary must be disclosed as such and loses generic-mechanism credit.

### ERC-3: missing topology and graph error

Attack the mechanism with:

- 5%, 10%, 20%, 40% missing dependency edges;
- spurious edges;
- timestamp jitter;
- sensor dropout;
- hidden intermediate nodes;
- schema changes.

Measure graceful degradation rather than binary survival.

### ERC-4: multiple simultaneous faults

Single-fault sparsity is removed.

Require explicit multi-root support recovery, bounded packets, and no collapse into one convenient root.

### ERC-5: prospective hidden workload

A third party or isolated operator freezes unseen incidents before execution. The development process receives no labels.

Only this stage can materially upgrade a transfer/generalization claim.

## 7. Hard controls inherited from other disciplines

Later stages must compare against serious controls rather than generic retrieval alone:

- dynamic/backward slicing where applicable;
- spectrum/statistical fault localization;
- BARO and RCAEval's causal/graph/multi-source baselines;
- full-history/oracle bounds;
- exact structured lookup where structure makes the answer trivial;
- minimal-witness/provenance methods where the task reduces to a database derivation;
- domain-standard fault-diagnosis baselines for chemical process and power-system experiments.

If an established transparent method matches ERC, that is a useful result and ERC receives no mechanism novelty credit.

## 8. Compression is not enough

A tiny packet is valuable only if it preserves the registered decision.

Always report jointly:

- decision accuracy;
- packet size;
- raw-to-packet byte ratio;
- support/witness recall;
- provenance correctness;
- runtime and memory;
- error by graph size/path length/distractor load;
- performance of the strongest simpler control.

Never report compression alone as an intelligence or architecture advance.

## 9. Counterfactual deletion test

A packet should eventually survive a stronger notion of necessity.

For each retained record, remove it and recompute the registered decision. Classify the record as:

- necessary;
- redundant but corroborating;
- irrelevant.

A mechanism with many irrelevant packet records fails mechanism-credit ablation even if packet size is under 16.

This is analogous to component ablation, minimal witnesses, and minimal explanation sets.

## 10. Research boundary

ERC does not currently establish:

- true causal identification from arbitrary observational data;
- a novel theory of sufficient statistics;
- a novel theory of database provenance;
- a new theory of protective relaying;
- general intelligence or semantic understanding;
- superiority over established RCA/fault-diagnosis methods;
- production utility or economic value.

The first question is smaller:

> Is there a simple, reproducible, bounded evidence-selection mechanism hiding inside the earlier MCO results that survives scale, serious nulls, and cross-domain transfer?

If no, stop.
If yes, keep simplifying until the smallest surviving mechanism is exposed.
