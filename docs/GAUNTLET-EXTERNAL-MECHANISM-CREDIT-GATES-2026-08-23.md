# Gauntlet External Mechanism-Credit Gates — 2026-08-23

## Status

```text
ENGINE:                         GENERIC / EXPERIMENT-AGNOSTIC
HISTORICAL SELF-TESTS:          PASS
EXTERNAL WITHHOLD CASE:         PASS
EXTERNAL PROVISIONAL-CREDIT:    PASS
EXTERNAL LINEAGE-HOLD CASE:     PASS
SEMI-AUTOMATIC MARKDOWN DRAFT:  PASS
HUMAN APPROVAL FIREWALL:        PASS
LATEST FULL CI RUN:             PASS
CI RUN ID:                      32636333877
CI JOB ID:                      97186558009
MERGE AUTHORIZATION:            NO
PRODUCT-MARKET FIT:             NOT ESTABLISHED
```

This record freezes the first external mechanism-credit discriminator set and
the first semi-automatic claim-extraction gate for Gauntlet. It does not alter
any GRI/DMC/MCO scientific verdict.

## Product thesis under test

> Given an apparent AI-system improvement, determine which mechanism actually
> deserves credit after integrity checks, matched controls, stronger or simpler
> baselines, ablations, resource constraints, and transfer evidence; then emit
> the strongest claim that survives.

The purpose of these gates is to establish that the engine can do more than
reject claims. A useful credit-assignment mechanism must distinguish at least:

1. a large score lead over an inadequate baseline;
2. a controlled ablation that supports narrow provisional credit;
3. an attractive comparison whose evidence lineage is not internally
   reconcilable;
4. unapproved machine extraction from human-authorized evidence.

All external cases here are retrospective. None creates new preregistered
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
README git blob: 404bc01c1d55eba1d644b742361ec356f3257ded
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

## Gate D — semi-automatic Markdown claim extraction

The manual external probes above establish the expected dispositions but are
not a scalable product interface. Gate D tests whether Gauntlet can ingest a
foreign source with **generic** extraction code, preserve human authority over
claim interpretation, and reproduce a manually verified disposition.

### New generic commands

```text
gauntlet draft-markdown
gauntlet approve-markdown
gauntlet autopsy
```

`draft-markdown` performs no credit assignment. It:

- hashes the source bytes and computes the Git blob identity;
- verifies an expected Git blob when supplied;
- catalogs Markdown numeric tables;
- records headings, line ranges, cells, numeric vectors and nearby context;
- marks likely control-language terms only as hints;
- explicitly refuses to infer candidate, baseline, metric direction or credit.

Its output authority is:

```text
UNAPPROVED_MARKDOWN_CLAIM_DRAFT
HUMAN_APPROVAL_REQUIRED
```

`approve-markdown` fails closed unless a human approval artifact:

- sets `approved=true`;
- binds the exact scanned Git blob and source revision;
- selects exactly one table;
- selects candidate and baseline rows;
- selects metric columns/vector positions and direction;
- binds required control phrases back to the source context.

Only then does it materialize a content-addressed evidence record and declarative
autopsy spec for the **unchanged** generic credit engine.

### Live foreign-source test

The CI gate downloads the pinned Embodied-Navigator README directly. No
Embodied-specific parser or probe is used in this path.

The generic scanner catalogs the source. A committed human approval artifact
selects:

```text
heading:          Controlled component attribution
candidate:        Full AT-Mem
baseline:         Full history
R2R SR:           metric vector index 2
RxR SR:           metric vector index 1
direction:        higher is better
```

The approval also binds the exact source statement that all variants share the
same policy, sensing inputs, validation splits, fixed SLAM controller and
evaluation protocol, with each block changing only the named component.

The generated evidence reproduces:

```text
R2R: 66.2 vs 61.9 -> +4.3
RxR: 65.7 vs 61.1 -> +4.6
```

The unchanged autopsy engine then returns:

```text
OUTCOME:             ADVANCE
CREDIT_DISPOSITION:  PROVISIONAL
PROSPECTIVE_CREDIT:  FALSE
```

### Failure controls

The regression suite verifies that materialization fails when:

- explicit approval is absent;
- approval is bound to the wrong source blob;
- an approved control sentence is not present in the source context.

This is the first successful transition from hand-written external probes to a
generic source-ingestion path with a human authorization boundary.

---

## Why the result matters

The same generic engine now produces three different external outcomes without
embedding project-specific names in decision code:

```text
large win + weak comparator
    -> STRONG_BASELINE_MISSING / WITHHELD

matched controlled ablation + consistent positive deltas
    -> ADVANCE / PROVISIONAL

large matched-budget win + unresolved source lineage
    -> INTEGRITY_INVALID / UNASSESSED
```

The semi-automatic layer additionally demonstrates:

```text
machine source extraction
    -> NO AUTHORITY

content-bound human selection + verified source controls
    -> evidence/spec materialization

unchanged generic autopsy engine
    -> mechanical disposition
```

This is evidence that Gauntlet is not merely a score threshold tool, not a
hard-coded rejection machine, and not an autonomous model allowed to decide what
a paper means. It is becoming a rule-bound claim-credit workflow.

## What remains unproven

The current gates do not establish:

- reliable extraction from arbitrary PDF layouts, prose-only papers or complex
  nested tables;
- automatic identification of the *right* candidate, baseline or metric;
- automatic detection of every confound or missing control;
- independent reproduction of external experiments;
- correctness of every author-reported metric;
- benchmark external validity;
- causal attribution beyond the approved controlled comparison;
- customer demand or willingness to pay;
- superiority over adjacent evaluation, audit, or research-review products;
- a durable commercial moat.

The broad evaluation-integrity/preregistration/attestation space has direct and
near-direct competitors. The differentiated thesis remains **mechanism-credit
autopsy**, not generic eval logging.

## Next product gate

Do not build a dashboard yet.

The next discriminator is **evidence-request generation and negative-case
semi-automation**.

Gauntlet should scan a foreign source, build a generic checklist for the claim,
and explicitly mark unresolved fields such as:

```text
candidate identity
baseline strength
model parity
budget parity
dataset/split parity
metric direction
ablation isolation
source lineage
uncertainty / replication
```

Then it must reproduce the AMB `STRONG_BASELINE_MISSING` disposition and the
PRO-LONG lineage hold through the generic drafting path, using human approval
only to confirm source interpretation—not hand-written case-specific Python.

If the evidence-request layer cannot surface those deficiencies reliably, keep
Gauntlet as a rigorous internal research tool rather than expanding it into a
product.
