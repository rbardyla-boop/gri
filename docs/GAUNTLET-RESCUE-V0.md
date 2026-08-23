# Gauntlet Rescue v0

## BLUF

The tested general AI-memory/state-compiler architecture remains terminally failed. This branch does not reopen it.

Gauntlet extracts a different asset from the repository: the machinery used to determine whether an AI evaluation result is admissible evidence.

The extraction works as engineering. The first broad product thesis does **not** yet survive competitive review.

```text
EVALUATION-INTEGRITY KERNEL:      WORKING
GENERIC CLAIM-LOCK PRODUCT:       DIRECT MARKET OVERLAP
FOREIGN INSPECT AUDIT:            WORKING
COMMERCIAL DIFFERENTIATION:       NOT ESTABLISHED
MAIN MERGE:                       NOT AUTHORIZED
NEXT THESIS:                      MECHANISM AUTOPSY / CREDIT ASSIGNMENT
```

See `docs/GAUNTLET-COMPETITIVE-REALITY-2026-08-23.md` for the competitive collision and next falsification gate.

## Why this branch exists

The project repeatedly caught failures that a normal score dashboard would not solve:

- recency leakage produced a false learned-memory win;
- transparent baselines removed learned-component credit;
- model-response instability invalidated an accounting claim;
- compiler-owned provenance and model-copied provenance diverged;
- a narrow real-telemetry success failed to transfer to a disjoint causal task;
- the final negative result remained stable and replayable.

The surviving capability is not "better memory." It is the combination of evidence integrity and **removing credit from mechanisms that do not survive stronger controls**.

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
9. **Foreign Inspect audit** — conservatively classify which properties are actually evidenced by an Inspect AI JSON EvalLog and exported run configuration.

The core uses the Python standard library. The Inspect adapter parses exported artifacts and does not require Inspect at runtime.

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

That means only that the toy demo satisfied its frozen gates. It is not scientific or commercial evidence for Gauntlet itself.

## Retrospective self-audit of MCO-05

This branch includes a generic retrospective spec for the already-finished MCO-05 result:

```bash
gauntlet audit-result \
  examples/gauntlet/mco05_retrospective.toml \
  artifacts/mco05/scientific/MCO05_VERDICT.json
```

The generic gate engine reports:

```text
EVIDENCE_CLASS: RETROSPECTIVE_AUDIT
STATE: NO_ESTABLISHED_ADVANTAGE
```

The comparison gate alone passes because the state packet leads hybrid RAG by more than five points. The absolute candidate-recall, packet-quality, adversarial, and no-code gates fail. This is the required behavior: a small baseline win cannot override failed preregistered quality gates.

The retrospective example is not a new preregistration. MCO-05's original frozen experiment remains the scientific authority.

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

Gauntlet v0 therefore refuses to claim protected-root enforcement for arbitrary subprocess runs. A serious agent-evaluation product would need a second isolation backend using containers, namespaces/Landlock/seccomp, or an external sequestered runner.

## Foreign Inspect audit

Gauntlet can audit an Inspect AI JSON EvalLog and optional exported run configuration:

```bash
gauntlet audit-inspect inspect-log.json --run-config inspect-run.json
```

The adapter deliberately distinguishes evidence available in the log from facts that are not established by the log alone.

It can verify or surface:

- log file identity;
- basic EvalLog structure;
- successful/incomplete/invalidated run status;
- task/model configuration metadata;
- dataset metadata;
- repository/source revision when logged;
- package versions;
- exported run-config artifact identity;
- result sample counts;
- sample targets/scores when present;
- model usage;
- mid-run configuration updates.

It deliberately returns `NOT_ESTABLISHED` for claims such as:

- cryptographic dataset-content identity when only dataset metadata is present;
- immutable provider model-weight identity;
- holdout isolation;
- preregistration timing;
- training-data contamination;
- independent replay when no replay receipt exists.

This adapter was validated in GitHub Actions against an actual Inspect `0.3.257` run generated with Inspect's built-in `mockllm` provider. The workflow generated the log, exported its run config, and Gauntlet audited those foreign artifacts successfully.

That establishes adapter interoperability. It does not establish a product moat.

## Threat model

v0 is designed to detect or prevent:

- post-freeze modification of declared inputs;
- silent spec changes;
- manifest tampering;
- result files that are not bound to the run receipt;
- tampered receipts;
- run/replay output mismatch;
- missing declared outputs;
- accidental protected-label reads in guarded Python runs;
- subprocess or network escape from guarded Python runs when disabled;
- path traversal in declared inputs;
- relative candidate wins that fail absolute quality gates;
- retrospective evidence being mislabeled as preregistered.

v0 does **not** yet detect:

- training-data contamination inside a pretrained model;
- benchmark answers memorized before the run;
- hostile native code escaping a Python audit hook;
- semantic grader gaming unless a scanner or task-specific check detects it;
- selective publication across multiple separately frozen experiments;
- organizational/process fraud outside the recorded artifact chain;
- whether the benchmark itself is externally valid;
- whether a learned mechanism deserves causal credit for an observed performance difference.

That last item is now the next rescue target.

## Competitive boundary

Gauntlet is not intended to replace Braintrust, Langfuse, Inspect, Phoenix, or another experiment/observability system.

More importantly, the first broad integrity framing directly overlaps newer systems such as Falsify/PRML, Authensor, AgenC's evaluation contract, and benchmark-integrity scanners such as BenchJack.

Therefore this branch is currently an **engineering foundation**, not an authorized standalone product thesis.

The next candidate differentiator is:

> **Mechanism autopsy:** given an apparent AI-system improvement, determine whether the claimed component deserves credit after matched baselines, simpler transparent/null replacements, component ablations, resource accounting, transfer tests, and absolute-quality gates.

## Current verification

The rescue branch currently passes on clean GitHub-hosted Linux/Python 3.11 CI:

- 18 targeted Gauntlet regression/manipulation/foreign-log tests;
- the existing project terminal-verdict verifier;
- generic retrospective reproduction of the MCO-05 negative disposition;
- full freeze -> verify -> run -> replay -> verdict demonstration;
- a real Inspect `0.3.257` generated foreign-log/config audit.

The deliberate manipulation suite covers:

- frozen input mutation;
- frozen spec mutation;
- manifest tampering;
- result tampering;
- nondeterministic replay;
- missing output;
- protected-root false-isolation claim;
- protected-label access;
- subprocess escape;
- network escape;
- declared path escape.

An early manipulation-suite commit had a syntax error in the test itself. CI failed collection; the test was repaired without weakening the integrity behavior. The subsequent run passed.

## Merge gate

Do **not** merge this branch into `main` merely because the implementation passes.

Before a merge is justified, the rescue thesis must pass a product-discovery gate that demonstrates value beyond ordinary preregistration/hash/replay tooling.

Current proposed gate:

1. implement a minimal generic mechanism-credit/strong-null engine;
2. reproduce historical DMC-05A, DMC-05R, MCO-03 and MCO-05 claim downgrades without experiment-specific decision code;
3. test the engine on at least one external public AI evaluation claim;
4. require an actionable claim-narrowing or credit-assignment finding that is not equivalent to simple tamper detection or threshold verification.

If that fails, preserve Gauntlet v0 as useful research infrastructure and stop the product pivot.

## Current maturity

```text
EXTRACTED MECHANISMS:            REAL
GENERIC V0 IMPLEMENTATION:       WORKING ON RESCUE BRANCH
TARGETED TESTS:                  18 PASS IN CI
MCO-05 RETROSPECTIVE AUDIT:      PASS
END-TO-END FREEZE/REPLAY:        PASS
REAL INSPECT FOREIGN-LOG AUDIT:  PASS
OS-LEVEL ISOLATION:              NOT IMPLEMENTED
GENERIC EVAL-INTEGRITY MOAT:     NOT ESTABLISHED / COMPETITIVE COLLISION
MECHANISM-AUTOPSY THESIS:        PLAUSIBLE / UNVALIDATED
CUSTOMER VALIDATION:             NONE
COMMERCIAL CLAIM:                NOT ESTABLISHED
MAIN-BRANCH MERGE:               NOT AUTHORIZED
```
