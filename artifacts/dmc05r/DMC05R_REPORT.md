# DMC-05R — Recency Confound Repair

Terminal state: `DMC_05R_TRANSPARENT_INDEX_DOMINATES`  
Verification verdict: **PASS**  
Frozen DMC established non-recency retention, but transparent utility indexing dominated it.

## Claim under test

When certified irrelevant writes are moved behind the last task-relevant write,
frozen DMC-04B preserves useful older state materially better than Recent-16.
Selection credit additionally requires a material win over equally informed
transparent utility indexing at the same 16-record capacity.

## Check

```bash
python3 scripts/run_dmc05r.py
python3 -m pytest -q tests/test_dmc05r.py
```

The run uses 592 frozen source cases, deterministic tails `0, 8, 16, 32, 64,
256`, 2,376 valid core variants, five frozen DMC seed pairs, and 24 separate
`SURPRISE_DEPENDENCY` cases.

## Verdict

`DMC_05R_TRANSPARENT_INDEX_DOMINATES`. The primary non-recency gate is
`PASS`;
the architecture-level selection-advantage gate is
`FAIL`.

## Core primary results

| System | Critical recall | Answer accuracy | Persistent records | Persistent bytes | Online ms/case |
|---|---:|---:|---:|---:|---:|
| Recent-16 | 0.00% | 4.87% | 16.00 | 1605.2 | 1.055 |
| Frozen FIFO-16 | 7.55% | 9.28% | 16.00 | 1559.1 | 0.067 |
| Random-16 | 14.47% | 19.18% | 16.00 | 1578.2 | 2.071 |
| Exact structured | 100.00% | 100.00% | 376.75 | 92034.5 | 1.851 |
| Conventional retrieval | 100.00% | 100.00% | 376.75 | 91911.6 | 1.815 |
| Transparent utility-16 | 100.00% | 100.00% | 16.00 | 4581.1 | 25.437 |
| DMC-04B frozen | 100.00% | 100.00% | 16.00 | 9487.1 | 30.449 |

| Irrelevant tail | Cases/run | Recent-16 recall | Transparent recall | DMC recall |
|---:|---:|---:|---:|---:|
| 0 | 592 | 100.00% | 100.00% | 100.00% |
| 8 | 512 | 0.78% | 100.00% | 100.00% |
| 16 | 512 | 0.00% | 100.00% | 100.00% |
| 32 | 416 | 0.00% | 100.00% | 100.00% |
| 64 | 256 | 0.00% | 100.00% | 100.00% |
| 256 | 88 | 0.00% | 100.00% | 100.00% |

## Criteria

| Criterion | Result | Evidence |
|---|---|---|
| `tail_zero_anchor` | PASS | `{"dmc04b":1.0,"recent_window_16":1.0,"transparent_utility_index_16":1.0}` |
| `all_history_answer_invariance` | PASS | `{"conventional_retrieval":{"0":1.0,"16":1.0,"256":1.0,"32":1.0,"64":1.0,"8":1.0},"exact_structured":{"0":1.0,"16":1.0,"256":1.0,"32":1.0,"64":1.0,"8":1.0}}` |
| `recent_primary_collapse` | PASS | `0.0` |
| `dmc_primary_survival` | PASS | `{"answer_accuracy":1.0,"critical_recall":1.0}` |
| `material_nonrecency_gap` | PASS | `1.0` |
| `nonrecency_retention_pass` | PASS | `{"dmc_critical_recall":1.0,"gap":1.0,"recent_critical_recall":0.0}` |
| `selection_advantage` | FAIL | `{"answer_accuracy_gap":0.0,"critical_recall_gap":0.0}` |
| `transparent_capability_match` | PASS | `{"dmc_answer_accuracy":1.0,"dmc_critical_recall":1.0,"transparent_answer_accuracy":1.0,"transparent_critical_recall":1.0}` |
| `transparent_resource_dominance` | PASS | `{"dimensions":{"historical_training_required":{"dmc04b":1.0,"pass":true,"transparent":0.0},"learned_forward_calls":{"dmc04b":4.0,"pass":true,"transparent":0.0},"maximum_working_set_records":{"dmc04b":16.0,"pass":true,"transparent":16.0},"online_wall_ns":{"dmc04b":30449030.245125785,"pass":true,"transparent":25437051.02044025},"persistent_records":{"dmc04b":16.0,"pass":true,"transparent":16.0},"persistent_serialized_bytes":{"dmc04b":9487.110849056604,"pass":true,"transparent":4581.148584905661},"records_inspected_query":{"dmc04b":16.0,"pass":true,"transparent":16.0},"working_set_serialized_bytes":{"dmc04b":3111.8993710691825,"pass":true,"transparent":1511.9913522012578}},"pass":true}` |
| `transparent_index_dominates` | PASS | `{"pass":true}` |

## Assumption register

| Assumption | Status | Evidence |
|---|---|---|
| Relocated records are answer-irrelevant and dependency-free | VERIFIED | Every variant passed record-membership, scope, salience, feature, supersession, payload, and order invariants in `variant_manifest.json`. |
| Counterfactuals preserve the frozen task answer | VERIFIED | Exact structured and conventional all-history systems are checked at every tail; target/query/oracle payloads are unchanged. |
| DMC and transparent selection receive equal utility information | VERIFIED | Runtime classifier firewalls and exact observed-field equality are recorded in `information_parity.json`. |
| Optimized execution is the frozen DMC mechanism | VERIFIED | 2960/2960 frozen-receipt comparisons and 50 direct boundary comparisons passed. |
| Historical learned cost was free | REFUTED | 10,880 heterogeneous optimizer steps are reconstructed; wall time, energy, and dollar cost remain `TRAINING_COST_UNKNOWN`. |
| Synthetic behavior transfers to real language | UNFALSIFIABLE HERE | No language, tokenizer, or language-model inference run is authorized in DMC-05R. |

## Credit assignment

The manipulated variable is stream position only: record payloads and all
semantic ordering are frozen. Recent-16 is the temporal-order counterfactual;
transparent utility-16 isolates whether explicit utility information, rather
than learned selection, causes survival. No selection credit is assigned merely
for beating FIFO or recency.

## SURPRISE_DEPENDENCY (exploratory, nonterminal)

| System | Critical recall | Answer accuracy |
|---|---:|---:|
| Recent-16 | 0.00% | 0.00% |
| Frozen FIFO-16 | 100.00% | 100.00% |
| Random-16 | 8.33% | 8.33% |
| Exact structured | 100.00% | 100.00% |
| Conventional retrieval | 100.00% | 100.00% |
| Transparent utility-16 | 0.00% | 0.00% |
| DMC-04B frozen | 0.00% | 0.00% |

This subset changes future utility only after ingestion. It does not enter the
terminal decision and does not authorize redesign after failure.

## Verification gap

This result is self-verified in one local execution environment; no independent
agent context was available. Absolute wall timings are machine-specific. The
test remains synthetic structured memory with no tokenizer or real model-cost
measurement, and historical training wall time, energy, and dollar cost are
unknown.

## Stop/continue

Stop learned retention in this synthetic family and keep DMC-05B blocked; the equally informed transparent selector is the branch-stop control.

## Maturity status

**Mature for this synthetic claim.** The claim is defined, compressed into a
frozen transformation and selector specification, tested, falsifiable,
replayed, and compared against recency, random, FIFO, exact, conventional, and
equal-information transparent variants. It is not evidence of real-language
or deployment maturity.

## Training accounting

- Reconstructed DMC suite optimizer steps: **10,880**.
- Online optimizer steps in DMC-05R: **0**.
- Historical wall time, energy, and dollar cost: **`TRAINING_COST_UNKNOWN`**.
