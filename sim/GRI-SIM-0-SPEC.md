# GRI-SIM-0 — Bounded Primitive Laboratory

**Status:** TOOLING SPECIFICATION — NO SUCCESSOR MECHANISM AUTHORIZED

## 1. Purpose

Provide one reusable deterministic simulator for Small-Info / GRI experiments so new candidate cells can be tested without rebuilding fixture, precision, replay, serialization, decoder, budget, and evidence machinery every time.

The simulator must reduce engineering time without weakening preregistration. It is an execution shell, not a source of scientific authorization.

## 2. Separation of authority

GRI-SIM-0 has three layers.

### Frozen experiment layer
Owns:
- literal fixtures and split;
- input alphabet;
- optimizer and training limits;
- precision modes and q8 rule;
- fixed-decoder protocol;
- serialization/restart protocol;
- state/parameter/operation ceilings;
- opponent/control definitions;
- verdict logic;
- expected hashes.

### Candidate plugin layer
May provide only:
- persistent recurrent state implementation;
- recurrent transition;
- readout;
- explicitly authorized ablation constructors;
- declarative resource/accounting manifest.

The candidate receives no fixture label, task identifier, delay count, sequence index, future token, or verdict state during evaluation.

### Evidence layer
Owns:
- source/config/fixture/rules hashes;
- environment record;
- run receipt;
- deterministic replay comparison;
- budget/accounting audit status;
- terminal verdict.

## 3. Candidate runtime protocol

A candidate module implements the protocol in `candidate_protocol.py`.

The simulator owns the recurrence loop. On each active token it calls only:

```text
h_next = cell.step(token_id, h)
```

The cell does not receive sequence length, current step number, task name, fixture id, label, split, or query horizon.

The simulator calls:

```text
logits = cell.readout(h)
```

only at the frozen readout boundary.

This narrow interface is intended to make hidden clocks, phase variables, label leakage, and decoder-side task state harder to introduce accidentally.

## 4. Candidate manifest

Every candidate must declare before execution:

- authorization unit and source hash;
- persistent state slots and precision;
- trainable parameter count;
- fixed parameters/constants;
- recurrent operation count;
- query/readout operation count;
- selector/comparison cost;
- serialization fields;
- auxiliary state, history, counters, caches, lookups;
- authorized ablations;
- whether any transition class is external or internally computed;
- optimizer mode (`FROZEN_PROTOCOL` or `NONE` for preregistered nonlearned candidate).

Missing accounting fields fail closed.

## 5. Operation accounting rule

The simulator does not let a candidate self-certify a formal resource advantage.

A candidate may declare counts for fast preflight, but formal verdict requires a separate accounting audit marked `PASS`. If source performs a comparison, branch predicate, lookup, copy, nonlinear operation, or other counted primitive that is absent from the declaration, the run is `INCONCLUSIVE` or budget-failed according to the frozen experiment verdict.

This directly prevents a repeat of the GRI-02C selector ambiguity.

## 6. Precision execution

Precision behavior is experiment-owned.

For the current GRI-02B-style q8 mode:

```text
float32 transition arithmetic
→ clip state to [-1, 1]
→ scale by 127
→ round-to-nearest-even
→ clip integer to [-127, 127]
→ divide by 127
→ store quantized state before next recurrent step
```

A future experiment may freeze a different rule, but candidate code may not select precision post-result.

## 7. Decoder isolation

The simulator owns decoder fitting and evaluation.

- Decoder fit sees only the frozen fit split.
- Held-out states and labels are never used during fit.
- One fixed decoder per task unless the experiment freezes a different rule.
- Candidate code never receives the fitted decoder during recurrence.
- Wait-specific/phase-specific decoders are rejected when forbidden by the experiment manifest.

## 8. Replay and serialization

The simulator must be able to restart a candidate at every registered token boundary:

```text
run prefix
→ canonical serialize persistent state
→ fresh process/object
→ restore
→ run suffix
→ compare output and final state with uninterrupted run
```

Only declared persistent state may be serialized. Hidden Python object state, RNG state used as memory, caches, counters, and history buffers are forbidden unless explicitly authorized and budgeted.

## 9. Codex containment

For a candidate task, Codex receives a writable candidate directory and read-only references to the simulator and frozen experiment.

Codex instructions should state:

```text
DO NOT modify:
- GRI-SIM-0 core
- frozen experiment manifest
- fixture bank
- operation rules
- verdict logic
- parent/control implementations

MAY modify only:
- candidate source
- candidate manifest
- candidate-specific tests

DO NOT run a successor experiment unless an authorization file names it.
DO NOT change a failed candidate after the first scientific result.
```

The recommended Git layout is:

```text
gri-research/
  sim/
    gri_sim0.py
    candidate_protocol.py
    schemas/
  experiments/
    frozen/<experiment-id>/
    candidates/<candidate-id>/
  artifacts/results/
```

## 10. Fast loop versus scientific loop

### Development smoke
May run repeatedly and is clearly marked `DEV_SMOKE`. It cannot issue `ADVANTAGE`/`NO_ADVANTAGE`.

### Frozen scientific run
Requires:
- authorization id;
- frozen candidate manifest;
- exact source hash;
- exact experiment hash;
- fresh output location;
- replay;
- accounting audit;
- no post-result modification.

This lets Codex iterate quickly during development without contaminating the one-shot frozen evaluation.

## 11. Current project boundary

GRI-SIM-0 is authorized only as reusable testing infrastructure. It does not answer the open selector-cost question and does not authorize any GRI successor mechanism.

The current canonical scientific state remains:

```text
GRI-01:    CLOSED — BOUNDED NEGATIVE
GRI-02C:   ALGORITHMIC FINDING SUPPORTED
GRI-02C.1: FORMAL GRI02_NO_ADVANTAGE
MINIMALITY: NOT ESTABLISHED
LOWER BOUND: NOT PROVEN
SUCCESSOR:  NOT AUTHORIZED
```
