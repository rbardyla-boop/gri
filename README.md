# GRI Gauntlet

GRI Gauntlet is a fail-closed command-line tool for checking **what an AI evaluation actually proves**.

It was built inside the GRI research program after several promising-looking experiments failed for different reasons: weak baselines, confounds, transfer failures, evidence-lineage problems, or simpler transparent methods doing the same job. The useful part that survived was the evaluation discipline itself.

In plain English, Gauntlet is meant to answer questions like:

> “This system scored higher. Was the claimed mechanism really responsible, or was the comparison too weak to justify that claim?”

Gauntlet does not use an LLM as the scientific authority. Machine extraction may collect evidence, but claim selection and negative-signal approval remain explicitly human-bound before the mechanical credit engine runs.

## Current status

**Research alpha.** The integrity kernel and mechanism-credit engine are working and continuously tested. External retrospective gates currently demonstrate three different outcomes:

- a large score lead over an explicitly weak comparator -> **credit withheld**;
- a controlled matched-policy ablation with positive deltas -> **provisional credit**;
- a large reported lead with unresolved source lineage -> **credit unassessed**.

These are evidence that the rules can distinguish different cases. They are **not** evidence of product-market fit, autonomous paper understanding, or universal scientific correctness.

## What it does

Gauntlet currently provides five related functions:

1. **Freeze and replay experiments** — bind a declared experiment to exact files, configuration, repository state, outputs, and replay checks.
2. **Audit existing results** — apply explicit gates to already-produced results without pretending the audit was preregistered.
3. **Mechanism-credit autopsy** — combine positive and invalidating signals using fixed precedence and emit the strongest surviving claim.
4. **Human-gated Markdown extraction** — catalog comparison tables from a foreign Markdown source, request missing evidence, bind a human-approved comparison to exact source bytes, then feed it to the unchanged credit engine.
5. **Foreign log audit** — conservatively inspect supported evaluation logs such as Inspect AI JSON without inventing evidence that is absent from the log.

## Installation

Python 3.11 or newer is required.

For development from a clone:

```bash
git clone https://github.com/rbardyla-boop/gri.git
cd gri
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
gri-gauntlet --version
```

The legacy `gauntlet` command remains available as an alias. `gri-gauntlet` is the preferred public command because several unrelated projects already use the name “Gauntlet.”

## Smallest useful demo

The repository includes a frozen end-to-end example:

```bash
gri-gauntlet freeze examples/gauntlet/demo.toml
gri-gauntlet verify .gauntlet/freeze.json
gri-gauntlet run .gauntlet/freeze.json --run-id live
gri-gauntlet replay \
  .gauntlet/freeze.json \
  .gauntlet/runs/live.json \
  --run-id replay
gri-gauntlet verdict \
  .gauntlet/freeze.json \
  .gauntlet/runs/live.json \
  --replay .gauntlet/replays/replay.json
```

A successful preregistered demo should end with an `ADVANCE` state only when the bound integrity checks and declared gates pass.

## Mechanism-credit autopsy

A declarative autopsy spec describes the credit target, evidence sources, and signals. The engine uses fixed precedence so a raw score improvement cannot override a stronger invalidating condition.

Examples of outcomes include:

```text
ADVANCE
STRONG_BASELINE_MISSING
CONFOUND_EXPLAINS_ADVANTAGE
TRANSPARENT_NULL_DOMINATES
COMPONENT_UNNECESSARY
TRANSFER_FAILURE
INTEGRITY_INVALID
```

The output also records whether credit is `PROVISIONAL`, `WITHHELD`, or `UNASSESSED` and emits the strongest claim that survives.

Run an existing autopsy with:

```bash
gri-gauntlet autopsy examples/gauntlet/autopsy/mco05.toml
```

## Human-gated foreign Markdown workflow

The scanner deliberately has **no authority to choose the winner**.

First, catalog a source:

```bash
gri-gauntlet draft-markdown README.md \
  --output .gauntlet/draft.json \
  --source-uri https://example.org/exact-source \
  --source-revision exact-revision
```

The draft records tables and unresolved evidence requests such as:

- baseline strength;
- model/policy parity;
- compute or action-budget parity;
- dataset/split parity;
- ablation isolation;
- source lineage;
- uncertainty and replication.

It also records that candidate, baseline, metric direction, negative signals, and credit decision have **not** been inferred.

A human approval artifact must then bind the exact source blob/revision and explicitly select the relevant comparison and any source-backed facts:

```bash
gri-gauntlet approve-markdown \
  .gauntlet/draft.json \
  approval.json \
  --output-dir .gauntlet/generated/example

gri-gauntlet autopsy .gauntlet/generated/example/autopsy.toml
```

If the source changed, the approval points at the wrong blob, an approved quotation is absent, or the selected comparison is ambiguous, materialization fails closed.

## Inspect AI log audit

For an external Inspect AI JSON log:

```bash
gri-gauntlet audit-inspect eval-log.json
```

Gauntlet distinguishes evidence actually present in the log from evidence that remains unestablished. A structurally valid run log does not automatically prove dataset identity, holdout isolation, preregistration, or claim admissibility.

## Evidence already in this repository

The repository preserves the failed and successful GRI/DMC/MCO research branches that produced the tooling. Important records include:

- `PROJECT_TERMINAL_VERDICT.md`
- `docs/PROJECT-STATE-RECONCILIATION.md`
- `docs/GAUNTLET-EXTERNAL-MECHANISM-CREDIT-GATES-2026-08-23.md`
- `artifacts/PROJECT_TERMINAL_VERDICT.json`
- frozen experiment contracts, verdicts, receipts, hashes, and replay checks under `experiments/` and `artifacts/`.

Those records are historical scientific evidence. They are not rewritten to make the current product look better.

## Research boundary

Gauntlet currently supports this narrow claim:

> It is a rule-bound evaluation-integrity and mechanism-credit workflow that can preserve exact evidence boundaries, apply explicit signal precedence, and distinguish several externally sourced retrospective claim situations.

It does **not** currently establish:

- autonomous scientific review;
- independent reproduction of every external experiment;
- correctness of author-reported measurements;
- general causal inference from arbitrary papers;
- superiority over every evaluation platform;
- customer demand or willingness to pay;
- a durable commercial moat.

## Repository history

This repository began as **GRI — Geometric Recurrent Intelligence**, including WORLD-0 and later DMC/MCO experiments. Several original architecture hypotheses were rejected by their own frozen tests. Those failures remain in the repository because preserving negative evidence is part of the project’s design.

The surviving product direction is the evaluation and credit-assignment machinery developed to make those failures difficult to explain away after the fact.

## Development

Install the test dependencies and run the Gauntlet regression suite:

```bash
python -m pip install -e '.[test]'
pytest \
  tests/test_gauntlet.py \
  tests/test_gauntlet_manipulations.py \
  tests/test_gauntlet_inspect_adapter.py \
  tests/test_gauntlet_autopsy.py \
  tests/test_gauntlet_claim_draft.py
```

Historical research modules remain in `src/` but are intentionally excluded from the `gri-gauntlet` wheel. Install research dependencies only when working on those archived/research paths:

```bash
python -m pip install -e '.[test,research]'
```

## Distribution status

A clean wheel/source-distribution gate, fresh-install smoke test, release checklist, and public distribution plan are being maintained in `docs/DISTRIBUTION-READINESS.md`.

No license has been selected in this repository yet. That is a deliberate release blocker rather than something the tooling should silently decide for the project owner.
