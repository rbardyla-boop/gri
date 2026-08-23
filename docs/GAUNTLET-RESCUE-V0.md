# Gauntlet Rescue v0

## BLUF

The tested general AI-memory/state-compiler architecture remains terminally failed. This branch does not reopen it.

Gauntlet extracts a different asset from the repository: the machinery used to determine whether an AI evaluation result is admissible evidence.

Working product thesis:

> **Gauntlet is an evaluation-integrity firewall: freeze the test, bind the inputs, isolate protected truth, run the candidate, replay it, and mechanically decide whether the claimed result follows from the frozen gates.**

This is a new product thesis. It inherits engineering mechanisms from GRI/DMC/MCO, but it inherits no architecture, product, or world-impact credit from those experiments.

## Why this branch exists

The project repeatedly caught failures that a normal score dashboard would not solve:

- recency leakage produced a false learned-memory win;
- transparent baselines removed learned-component credit;
- model-response instability invalidated an accounting claim;
- compiler-owned provenance and model-copied provenance diverged;
- a narrow real-telemetry success failed to transfer to a disjoint causal task;
- the final negative result remained stable and replayable.

The surviving capability is therefore not "better memory." It is **making it hard to fool ourselves about an evaluation**.

## v0 scope

Gauntlet v0 implements only a small, auditable kernel:

1. **Freeze** — hash the experiment spec and declared input files; optionally require a clean Git worktree and exact commit.
2. **Verify** — recompute the frozen hashes before a run.
3. **Run** — execute the exact frozen command and bind declared output hashes into a content-addressed receipt.
4. **Protected Python run** — for in-process Python evaluations, install an audit-hook guard that blocks access to protected roots and can deny subprocess/network escape paths.
5. **Replay** — rerun the frozen command and compare declared outputs byte-for-byte.
6. **Mechanical gates** — apply absolute gates before relative candidate-vs-baseline claims.
7. **Evidence class** — distinguish a retrospective audit from a preregistered frozen run.
8. **Verdict binding** — bind the freeze, run receipt, result file and optional replay before emitting a terminal state.

The core uses the Python standard library. It does not require an LLM.

## Commands

Install the branch in editable mode:

```bash
python -m pip install -e .
```

Run the deterministic demonstration:

```bash
gauntlet freeze examples/gauntlet/demo.toml
gauntlet verify .gauntlet/freeze.json
gauntlet run .gauntlet/freeze.json --run-id live
gauntlet replay .gauntlet/freeze.json .gauntlet/runs/live.json --run-id replay
gauntlet verdict \
  .gauntlet/freeze.json \
  .gauntlet/runs/live.json \
  --replay .gauntlet/replays/replay.json
```

Expected terminal state for the demo:

```text
ADVANCE
```

That means only that the toy demo satisfied its frozen gates. It is not scientific evidence for Gauntlet itself.

## Retrospective self-audit of MCO-05

This branch includes a generic retrospective spec for the already-finished MCO-05 result:

```bash
gauntlet audit-result \
  examples/gauntlet/mco05_retrospective.toml \
  artifacts/mco05/scientific/MCO05_VERDICT.json
```

The generic gate engine should report:

```text
EVIDENCE_CLASS: RETROSPECTIVE_AUDIT
STATE: NO_ESTABLISHED_ADVANTAGE
```

The comparison gate alone passes because the state packet leads hybrid RAG by more than five points. The absolute candidate-recall, packet-quality, adversarial, and no-code gates fail. This is the required behavior: a small baseline win cannot override failed preregistered quality gates.

The retrospective example must never be described as a new preregistration. MCO-05's original frozen experiment remains the scientific authority.

## Minimal spec

Gauntlet accepts TOML or JSON. A prospective TOML spec can look like:

```toml
[experiment]
id = "candidate-vs-baseline"
require_clean_repo = true
require_same_commit = true

[freeze]
inputs = ["eval.py", "data/public.jsonl"]

[run]
mode = "subprocess"
command = ["python", "eval.py"]
outputs = ["result.json"]

[verdict]
result_file = "result.json"
require_replay = true

[[gates]]
name = "absolute_quality"
path = "candidate.accuracy"
op = ">="
value = 0.80
required = true

[comparison]
candidate_path = "candidate.accuracy"
baseline_path = "baseline.accuracy"
direction = "greater"
minimum_delta = 0.05
```

## Protected-truth mode

If labels, oracle data, or other protected truth exist locally, v0 can enforce a Python-level guard:

```toml
[freeze]
inputs = ["eval.py", "public_data/"]
protected = ["private_labels/"]

[run]
mode = "python"
entry = "eval.py"
args = []
outputs = ["result.json"]
deny_subprocess = true
deny_network = true
```

If the evaluated Python process attempts to open a protected path, Gauntlet fails closed with `GAUNTLET_HOLDOUT_VIOLATION`.

### Important limitation

The Python audit hook is **not an OS security sandbox**. It is useful for catching accidental and ordinary Python-level leakage. It does not establish containment against hostile native code, `ctypes`, kernel exploits, or every possible side channel.

Gauntlet v0 therefore refuses to claim protected-root enforcement for arbitrary subprocess runs. A serious agent-evaluation product needs a second isolation backend using containers, namespaces/Landlock/seccomp, or an external sequestered runner.

## Threat model

v0 is designed to detect or prevent:

- post-freeze modification of declared inputs;
- silent spec changes;
- result files that are not bound to the run receipt;
- tampered receipts;
- run/replay output mismatch;
- accidental protected-label reads in guarded Python runs;
- subprocess or network escape from guarded Python runs when disabled;
- relative candidate wins that fail absolute quality gates;
- retrospective evidence being mislabeled as preregistered.

v0 does **not** yet detect:

- training-data contamination inside a pretrained model;
- benchmark answers memorized before the run;
- hostile native code escaping a Python audit hook;
- semantic grader gaming unless a scanner or task-specific check detects it;
- selective publication across multiple separately frozen experiments;
- organizational/process fraud outside the recorded artifact chain;
- whether the benchmark itself is externally valid.

## Product boundary

Gauntlet is not intended to replace Braintrust, Langfuse, Inspect, Phoenix, or another experiment/observability system.

Those systems can remain the experiment runner and log store. Gauntlet should sit beside them and answer a narrower question:

> **What claims are this evaluation actually allowed to support?**

Potential adapters should import existing logs/configs, hash their identities, identify missing integrity evidence, and emit an evidence class rather than forcing teams to migrate their eval stack.

## v0 acceptance gates

Before this branch can be proposed for `main`, all of the following must hold:

- `tests/test_gauntlet.py` passes.
- Existing project tests are not broken by package discovery changes.
- The MCO-05 retrospective example returns `NO_ESTABLISHED_ADVANTAGE` without MCO-specific code in `src/gauntlet/`.
- A mutated frozen input is detected.
- A tampered run receipt forces `INTEGRITY_FAIL`.
- A protected-label read is blocked in guarded Python mode.
- A deterministic run replays with identical declared output hashes.
- The demo frozen verdict returns `ADVANCE` only after freeze, run, result binding and replay all pass.
- `main` remains unchanged until review.

## Next discriminators

Do not build a dashboard yet.

The next two product tests are:

1. **Foreign-log audit:** ingest an Inspect AI log plus exported run config and classify which integrity properties are verified, missing, or unverifiable.
2. **Manipulation suite:** create deliberately invalid evaluations (changed threshold, changed dataset, hidden-label read, dropped sample, selective retry, scorer edit, unequal baseline context, result tampering) and measure detection rate.

If Gauntlet cannot audit a foreign evaluation or cannot reliably detect the manipulation suite, stop this pivot rather than expanding the feature set.

## Current maturity

```text
EXTRACTED_MECHANISMS:      REAL
GENERIC V0 IMPLEMENTATION: THIS BRANCH
TARGETED TESTS:            REQUIRED BEFORE MERGE
FOREIGN EVAL SUPPORT:      NOT IMPLEMENTED
OS-LEVEL ISOLATION:        NOT IMPLEMENTED
CUSTOMER VALIDATION:       NONE
COMMERCIAL CLAIM:          NOT ESTABLISHED
```
