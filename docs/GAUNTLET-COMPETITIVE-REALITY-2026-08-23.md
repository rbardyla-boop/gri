# Gauntlet Competitive Reality — 2026-08-23

## BLUF

The first Gauntlet product framing — generic evaluation freezing, claim preregistration, replay, integrity gates, and attestation — is **not a defensible standalone differentiation claim**.

The engineering extraction is real and useful, but the market/research surface already contains closely overlapping systems.

```text
GENERIC_FREEZE_REPLAY_CLAIM_GATE: OVERLAPPING / NOT A MOAT
FOREIGN_LOG_AUDIT:                USEFUL FEATURE / NOT A MOAT
GENERIC EVAL-INTEGRITY PRODUCT:   DIFFERENTIATION NOT ESTABLISHED
MAIN-BRANCH MERGE:                NOT AUTHORIZED
```

The next rescue thesis is narrower:

> **Mechanism autopsy for AI claims:** automatically determine what actually earned an apparent performance advantage by forcing matched baselines, transparent nulls, ablations/interventions, cost accounting, transfer gates, and failure attribution before allowing an architecture-level claim.

That thesis is not yet established either. It requires its own falsification gate.

## Direct competitive collision

### Falsify / PRML

`studio-11-co/falsify` already implements a very close version of the generic freeze/claim-gate concept:

- preregister an AI/ML claim before evaluation;
- lock metric, threshold, dataset hash and seed with SHA-256;
- detect post-lock modification;
- run `init -> lock -> run -> verdict -> guard`;
- expose deterministic CI exit states;
- provide a GitHub Action and multiple language implementations.

Public source:

- https://github.com/studio-11-co/falsify
- https://github.com/marketplace/actions/prml-verify

This means Gauntlet cannot credibly claim that cryptographic claim locking plus CI verdicts is a new product category.

### Authensor

Authensor is already operating in evaluation-integrity auditing and attestation. Its public offering includes:

- pin verification for dataset revision, judge model and grading code;
- grader/judge pipeline review;
- oracle and dataset residency analysis;
- hardened re-grading of published results;
- a scoped attestation product;
- the Evaluator Trust Boundary (ETB) defect taxonomy and open scanner tooling.

Public source:

- https://www.authensor.com/
- https://www.authensor.com/etb

This overlaps the broad claim that the commercial wedge is simply "can this evaluation number be trusted?"

### AgenC evaluation contract

The public `tetsuo-ai/agenc-core` evaluation contract already demonstrates a sophisticated confirmatory-evidence architecture including:

- exact preregistration;
- private holdout custody;
- agent-safe projections;
- append-only evidence ledgers;
- external seals;
- randomized execution order;
- fixed stopping rules;
- bundle-bound re-derivation;
- explicit legacy/non-confirmatory evidence classes.

Public source:

- https://github.com/tetsuo-ai/agenc-core/blob/main/docs/evaluation-contract-v1.md

This is evidence that rigorous chain-of-custody evaluation contracts are not unique to this repository.

### Benchmark vulnerability scanners

BenchJack is already scanning agent benchmarks for evaluator vulnerabilities including leaked answers, weak isolation, prompt-injectable judges, logic gaps, trusting untrusted outputs, and excessive permissions.

Public source:

- https://github.com/benchjack/benchjack

Therefore a generic "find benchmark cheating/integrity problems" scanner is also a crowded direction.

## What Gauntlet v0 still proves

The collision does **not** invalidate the engineering work on this branch.

The branch has demonstrated that the repository's experiment-specific integrity mechanisms can be extracted into a generic kernel:

- frozen spec/input hashes;
- bound run receipts;
- deterministic replay;
- absolute gate precedence;
- result/receipt tamper detection;
- guarded Python holdout access;
- explicit retrospective vs preregistered evidence classes;
- conservative foreign Inspect-log audit.

It has also reproduced the correct MCO-05 disposition without MCO-specific code in the generic gate engine.

That is an engineering result. It is **not** evidence of product differentiation or customer demand.

## Why mechanism autopsy is a different question

The DMC/MCO research program did more than preserve evaluation integrity. It repeatedly changed the **credit assignment** for apparent wins:

```text
apparent learned-memory win
        -> recency-control intervention
        -> learned advantage disappears

learned selector survives repaired workload
        -> equally informed transparent null
        -> learned component receives no architecture credit

language boundary improves
        -> transparent compiler produces identical state
        -> learned extraction receives no credit

narrow real telemetry success
        -> disjoint workload
        -> transfer claim fails

packet beats RAG by a few points
        -> absolute quality / adversarial / no-code gates
        -> product claim still fails
```

The recurring output was not merely PASS/FAIL. It was:

> **Which mechanism is actually entitled to credit, which simpler null explains the result, and what is the strongest surviving claim?**

That is the next candidate product boundary.

## Adjacent work means this is not automatically unique

This direction also has adjacent research and tooling:

- automated AI-research systems already perform ablations and replication;
- counterfactual debugging tools can ablate components and re-run systems;
- benchmark-security tools search for reward hacking and evaluator vulnerabilities;
- research on causal credit assignment uses executed replay and counterfactual interventions.

Examples:

- https://github.com/counterfact-labs/counterfact
- https://github.com/benchjack/benchjack

Therefore "we run ablations" is not enough.

The possible differentiation is the **claim-level synthesis** across:

1. strong conventional baseline;
2. transparent/null replacement;
3. component ablation/intervention;
4. matched resource accounting;
5. absolute quality gates;
6. transfer/disjoint-workload gates;
7. failure taxonomy;
8. mechanical claim downgrade.

That combination remains a hypothesis until tested against external evaluation claims.

## Next falsification gate

Do not expand the product yet.

Build the smallest generic mechanism-credit engine that can consume declarative claim/control data and, without experiment-specific code, reproduce at least these historical diagnoses:

| Historical evidence | Required generic diagnosis |
|---|---|
| DMC-05A | confound/control removes architecture credit |
| DMC-05R | transparent null dominates learned selector |
| MCO-03 | transparent replacement makes learned component unnecessary |
| MCO-05 | transfer/absolute-quality failure despite a small relative lead |

The engine must not contain literal strings such as `DMC-05A`, `DMC-05R`, `MCO-03`, or `MCO-05` in its decision logic.

Then test it on at least one external public AI claim or evaluation repository. A viable signal is not "the tool runs." It must identify a claim-narrowing control, missing strong null, unmatched resource, transfer gap, or credit-assignment problem that is not already provided by simple preregistration/hash verification.

## Kill criteria

Stop the mechanism-autopsy pivot if any of the following becomes true:

- the historical diagnoses require experiment-specific hard-coding;
- the engine reduces to ordinary preregistration plus threshold comparison;
- a simpler existing tool already exposes the same claim-level diagnosis;
- external claims do not yield actionable credit-assignment findings;
- the tool cannot distinguish a mechanism failure from a benchmark/integrity failure;
- the output cannot be stated as a narrower falsifiable claim.

## Current company state

```text
ORIGINAL AI-MEMORY THESIS:          TERMINAL FAIL
TRANSPARENT COMPILER PRODUCT:       TERMINAL FAIL ON DISJOINT TRANSFER
GENERIC EVAL-INTEGRITY PIVOT:       ENGINEERING WORKS / MARKET COLLISION
FOREIGN INSPECT AUDIT:              WORKING FEATURE / NO MOAT CLAIM
MECHANISM-AUTOPSY THESIS:           PLAUSIBLE / UNVALIDATED
CUSTOMER DEMAND:                    UNKNOWN
COMMERCIAL DIFFERENTIATION:         NOT ESTABLISHED
```

The repository's strongest asset remains its willingness and machinery to remove credit from its own preferred mechanism when a simpler explanation survives. The rescue effort should test whether that can become a reusable tool before any further product build-out.
