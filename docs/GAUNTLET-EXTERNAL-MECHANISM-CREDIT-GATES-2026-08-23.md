# Gauntlet External Mechanism-Credit Gates — 2026-08-23

## Status

```text
ENGINE:                         GENERIC / EXPERIMENT-AGNOSTIC
HISTORICAL SELF-TESTS:          PASS
EXTERNAL WITHHOLD CASE:         PASS
EXTERNAL PROVISIONAL-CREDIT:    PASS
EXTERNAL LINEAGE-HOLD CASE:     PASS
FULL CI RUN:                    PASS
CI RUN ID:                      32636109010
CI JOB ID:                      97186005246
MERGE AUTHORIZATION:            NO
PRODUCT-MARKET FIT:             NOT ESTABLISHED
```

This record freezes the first external mechanism-credit discriminator set for
Gauntlet. It does not alter any GRI/DMC/MCO scientific verdict.

## Product thesis under test

> Given an apparent AI-system improvement, determine which mechanism actually
> deserves credit after integrity checks, matched controls, stronger or simpler
> baselines, ablations, resource constraints, and transfer evidence; then emit
> the strongest claim that survives.

The purpose of these gates is to establish that the engine can do more than
reject claims. A useful credit-assignment mechanism must be able to distinguish
at least three situations:

1. a large score lead over an inadequate baseline;
2. a controlled ablation that supports narrow provisional credit;
3. an attractive comparison whose evidence lineage is not internally
   reconcilable.

All three external cases are retrospective. None creates new preregistered
scientific evidence.

---

## Gate A — Agent Memory Benchmark

### Pinned source

```text
repository: AlekseiMarchenko/agent-memory-benchmark
commit:     9146ffa044109166b5d61146ebbf1c89fa544608
```

The pinned Layer-1 table reports:

```text
Central Intelligence overall:  90
In-Memory Baseline overall:     55
Central Intelligence semantic: 100
In-Memory Baseline semantic:      0
```

The benchmark itself states that the in-memory baseline uses exact keyword
matching rather than embeddings, is a floor, and is not a meaningful semantic
comparison. The pinned in-memory adapter confirms lexical query-word overlap.

### Mechanical signals

```text
ADVANCE:                  TRIGGERED
STRONG_BASELINE_MISSING:  TRIGGERED
```

Fixed precedence therefore produces:

```text
OUTCOME:             STRONG_BASELINE_MISSING
CREDIT_DISPOSITION:  WITHHELD
```

### Strongest surviving claim

> The published scores establish performance over the benchmark's lexical
> in-memory floor, but this comparison alone does not establish superiority
> over a strong semantic-memory baseline.

This is not a criticism of the benchmark authors for concealing the limitation;
the limitation is explicitly disclosed in the source.

---

## Gate B — Embodied-Navigator controlled memory ablation

### Pinned source

```text
repository: ZJU-OmniAI/Embodied-Navigator
commit:     2f82cbd5ae4cd3abe0c15da0d70dc8f1adb6f04d
```

The pinned README states that the controlled component-attribution variants use
the same Qwen2.5-VL-7B policy, sensing inputs, validation-unseen splits, fixed
non-learned SLAM controller, and evaluation protocol, and that each block changes
only its named component.

Within the Memory block, the reported success rates are:

```text
                         R2R-CE SR   RxR-CE SR
Full history                61.9        61.1
AT-Mem without STI          63.6        62.4
Full AT-Mem                 66.2        65.7
```

Therefore:

```text
Full AT-Mem - Full history:     +4.3 / +4.6 points
Full AT-Mem - AT-Mem w/o STI:   +2.6 / +3.3 points
```

### Mechanical signals

```text
ADVANCE:  TRIGGERED
```

No higher-precedence invalidating signal is registered for this pinned evidence.
The mechanical result is therefore:

```text
OUTCOME:             ADVANCE
CREDIT_DISPOSITION:  PROVISIONAL
```

### Strongest surviving claim

> On the pinned reported matched-policy validation-unseen ablation, Full
> Anchor-Trajectory Memory retains provisional conditional credit over
> full-history memory, with positive SR deltas on both R2R-CE and RxR-CE.

This does **not** establish general memory superiority, independent replication,
or prospective credit. Gauntlet did not rerun the training or evaluation.

---

## Gate C — PRO-LONG matched-budget re-score lineage

### Pinned source

```text
repository: alexisfox7/PRO-LONG
commit:     9d2f2d46fea8759ed494ce5b0166c7004a2e97c4
```

Three pinned public scorecards were inspected:

```text
prolong_r3_online_scorecards.txt
prolong_r3_online_scorecards_at500.txt
inprompt_r3_online_scorecards.txt
```

The published means are:

```text
PRO-LONG full run, 1000 actions:       50.2%
PRO-LONG scorecard at 500 cutoff:      45.6%
No-log / in-prompt, 500 actions:       24.7%
Matched-budget reported gap:           +20.9 points
```

The 500-action candidate and baseline scorecards match on the common published
backend/model, reasoning effort, online mode, grid mode, session mode, action
cap, and 500-action scoring budget.

However, the 500-action PRO-LONG scorecard explicitly describes itself as the
1,000-action run truncated/scored at a 500-action cutoff. Game-level provenance
does not fully reconcile with the pinned 1,000-action scorecard: at least some
replay identities and reported `full:` values differ between the two committed
files. The probe records the mismatching game IDs mechanically.

This does **not** establish that the 45.6% result is false. It establishes that
Gauntlet cannot currently verify the stated re-score lineage strongly enough to
use it as clean mechanism-credit evidence.

### Mechanical signals

```text
ADVANCE:             TRIGGERED
INTEGRITY_INVALID:   TRIGGERED
```

Fixed precedence therefore produces:

```text
OUTCOME:             INTEGRITY_INVALID
CREDIT_DISPOSITION:  UNASSESSED
```

### Strongest surviving claim

> The published 500-action comparison reports a positive full-log score gap,
> but the scorecard's claimed truncation lineage does not reconcile with the
> pinned 1,000-action source scorecard; mechanism credit remains unassessed
> until that provenance is reconciled.

---

## Why the three-case result matters

The same generic engine now produces three different outcomes on disjoint public
claims without embedding project-specific names in the decision code:

```text
large win + weak comparator
    -> STRONG_BASELINE_MISSING / WITHHELD

matched controlled ablation + consistent positive deltas
    -> ADVANCE / PROVISIONAL

large matched-budget win + unresolved source lineage
    -> INTEGRITY_INVALID / UNASSESSED
```

This is evidence that Gauntlet is not merely a score threshold tool and not a
hard-coded rejection machine. It is performing rule-bound claim-credit
assignment over externally sourced evidence.

## What remains unproven

The external gates do not establish:

- automatic extraction from arbitrary papers or repositories;
- independent reproduction of the external experiments;
- correctness of every author-reported metric;
- benchmark external validity;
- causal attribution beyond the registered controlled comparison;
- customer demand;
- willingness to pay;
- superiority over adjacent evaluation, audit, or research-review products;
- a durable commercial moat.

The broad evaluation-integrity/preregistration/attestation space has direct and
near-direct competitors. The differentiated thesis remains **mechanism-credit
autopsy**, not generic eval logging.

## Next product gate

Do not build a dashboard yet.

The next discriminator is a semi-automatic claim autopsy that starts from a
foreign public repository or evaluation artifact and produces a candidate
credit graph with evidence requests, while requiring human approval before any
mechanical signal becomes authoritative.

Minimum next gate:

1. ingest one public claim without a hand-written experiment-specific probe;
2. identify candidate, baseline, metric, budget and component delta;
3. identify at least one missing or conflicting evidence item when present;
4. emit a draft declarative autopsy spec;
5. require human confirmation of extracted facts;
6. run the unchanged generic credit engine;
7. reproduce the manually verified disposition.

If that cannot be done reliably, keep Gauntlet as a rigorous internal research
tool rather than expanding it into a product.
