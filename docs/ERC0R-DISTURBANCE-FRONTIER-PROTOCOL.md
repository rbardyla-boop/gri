# ERC-0R — Disturbance Frontier Successor

Status: PREREGISTERED PRE-EXECUTION
Date: 2026-08-23
Parent: ERC-0 terminal `ERC0_SYNTHETIC_FAIL`

## 1. Why this successor exists

ERC-0 is terminal and is not rescored or repaired.

Its registered 96-case result showed a specific post-result clue:

- anomalous ancestor coverage: 0.8125 top-1, 1.0000 top-3 overall;
- at 2048 nodes: 0.5000 top-1, 1.0000 top-3;
- topology-only and largest-anomaly controls: 0.0000 top-1.

Thus the true root remained inside a tiny dependency-aware support set even when top-1 discrimination collapsed at scale.

ERC-0R tests one separately disclosed hypothesis motivated by that observation. It cannot retroactively rescue ERC-0.

## 2. Cross-domain hypothesis

Protective relaying localizes faults by distinguishing the disturbed zone from the upstream healthy system. In a directed information/telemetry graph, a single propagating source should similarly form a **disturbance frontier**:

> an anomalous node with strong coherent disturbed evidence downstream and little coherent anomalous evidence upstream.

This is a source-localization heuristic, not a proof of counterfactual causality.

## 3. Frozen inherited machinery

ERC-0R inherits unchanged from ERC-0:

- graph generator;
- signal generator;
- robust local feature extraction;
- anomaly threshold `2.5`;
- source/provenance hashing;
- packet capacity `16`;
- random, topology-only, largest, earliest, ancestor-coverage, backward-slice and relay controls;
- no language model;
- no training/optimization;
- no hidden root label on candidate-facing objects.

ERC-0R uses a fresh seed namespace and does not reuse any ERC-0 result row.

## 4. Fresh population

Registered sizes:

- 32 nodes;
- 128 nodes;
- 512 nodes;
- 2048 nodes.

Registered cases: 32 per size, 128 total.

Fresh seed namespace:

```text
2026082400 + size * 1000 + ordinal
```

for ordinal `0..31`.

The runner must assert that no ERC-0 case ID is present.

## 5. New transparent rules

All rules use only candidate-visible graph structure and extracted observations.

For anomalous candidate `c`, define:

- `upstream_count(c)`: number of anomalous ancestors whose onset is no later than `c`;
- `upstream_weight(c)`: sum of those ancestors' anomaly scores divided by total anomalous score;
- `downstream_coverage(c)`: the inherited coherent downstream coverage fraction;
- `direct_upstream_count(c)`: number of anomalous direct parents whose onset is no later than `c`.

### 5.1 Quiet-parent rule

Rank anomalous candidates lexicographically by:

1. lower `direct_upstream_count`;
2. higher `downstream_coverage`;
3. earlier onset;
4. higher local anomaly score;
5. opaque node ID.

This is the simplest selective-protection analogue.

### 5.2 Disturbance-frontier rule

Rank anomalous candidates lexicographically by:

1. lower `upstream_count`;
2. lower `upstream_weight`;
3. higher `downstream_coverage`;
4. earlier onset;
5. higher local anomaly score;
6. opaque node ID.

There are no learned coefficients and no threshold fitted from ERC-0 rows.

## 6. Simplicity precedence

Outcome precedence:

1. `ERC0R_INTEGRITY_INVALID`
2. `ERC0R_CONSTRUCTION_SHORTCUT`
3. `ERC0R_NONTOPOLOGICAL_SUFFICIENT`
4. `ERC0R_ANCESTOR_COVERAGE_SUFFICIENT`
5. `ERC0R_QUIET_PARENT_SUFFICIENT`
6. `ERC0R_FRONTIER_ADVANCE`
7. `ERC0R_FRESH_SEED_FAIL`

If an inherited simpler rule clears quality gates and is within 0.02 top-1 of frontier, the simpler rule gets credit.

If quiet-parent clears gates and is within 0.02 of frontier, quiet-parent gets credit.

Frontier-specific credit requires a >= 0.05 top-1 advantage over the strongest simpler topology-aware rule.

## 7. Frozen quality gates

For an advancing/sufficient mechanism require:

- overall top-1 >= 0.90;
- top-1 >= 0.85 at every graph size;
- overall top-3 >= 0.98;
- accuracy loss from 32 to 2048 nodes <= 0.07;
- packet count <= 16 in 100% of cases;
- packet provenance = 1.00;
- exact deterministic replay = 1.00;
- topology-only top-1 < 0.35;
- largest-anomaly wrong fraction >= 0.30;
- topology-aware winner beats best non-topological observation control by >= 0.15.

Frontier-specific mechanism credit additionally requires >= 0.05 top-1 over the strongest simpler topology-aware method.

## 8. Interpretation

A PASS can establish only that one transparent source-frontier rule survives fresh samples from the same synthetic generator family at the registered scale.

It cannot establish:

- cross-domain transfer;
- real telemetry performance;
- independent replication;
- causal identification from arbitrary observations;
- a new fault-diagnosis theory;
- an AI-memory architecture.

If ERC-0R advances, the next step is not more synthetic tuning. The rule freezes and moves to a clean-room MCO-04 reproduction and then a cross-domain transfer gate.
