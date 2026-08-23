# GRI-02C — Identity-Preserve Cell

## Raw execution result

```text
GRI02_ADVANTAGE
```

This is the raw result produced before the selector-accounting closure. The
formal result for the frozen executable candidate is recorded in
`GRI-02C.1-RESULT.md`.

The single authorized candidate passed every required gate across seeds
`20260820`, `20260821`, and `20260822`.

## Candidate

```text
state width:             8
persistent state slots: 8
auxiliary state:         0
history buffer:          0
step counter:            0
phase variable:          0
preserve parameters:     0
parameters:              170
```

The only preserve token is `WAIT`:

```text
WAIT       -> h_next = h
all others -> h_next = tanh(W h + E[token] + b)
query      -> transform, then frozen binary readout
```

The raw candidate declaration described transition selection as a frozen
token-semantic dispatch using no hidden state, elapsed step, task identity,
label, or sequence position. GRI-02C.1 separately audits whether that semantic
dispatch was actually external to the executable candidate.

## Gate results

- Preserve fixtures: **PASS** for every seed and required mode.
- Transform fixtures: **PASS** for every seed and required mode.
- Fixed decoder: **PASS**; fit only on B’s fit split, evaluated on held-out
  states with no wait-specific decoder.
- Float64, float32, and recurrent q8: **PASS**.
- Float16 and bfloat16 stress modes: **PASS**.
- Minimum required fixed-decoder geometric margin: `0.1102362201`.
- Parent opponent: **PASS**; parent held-out accuracy was approximately
  `0.50–0.529`.
- Stateless opponent: **PASS**; held-out accuracy was `0.50`.
- No-preserve ablation: **FAILS**, as required.
- No-transform ablation: **FAILS**, as required.
- No-recurrence ablation: **FAILS**, as required.
- Parameter budget: **PASS**; the raw receipt’s operation-budget declaration
  passed before the selector audit.
- Formal operation-budget closure: **FAIL** after charging the executable
  selector comparison under GRI-02B’s frozen rules.
- Deterministic replay: **PASS**.
- Existing regression suite: **PASS**, 36 tests.

## Interpretation

Within this frozen fixture family and training protocol, giving semantic
`WAIT` an explicit identity transition solved the precise GRI-01 failure. The
ablation pattern supplies causal credit: removing preservation loses the
long-delay result, while removing transformation or recurrence loses the
event-dependent result.

The separate selector audit found that the current executable candidate
computes `ids == self.wait_index` internally rather than receiving an external
transition-class signal. Charging that comparison produces 98 recurrent and
119 recurrent-plus-query operations, over the frozen 97 and 118 ceilings.
Accordingly, the algorithmic finding is supported, but the formal frozen
verdict is `GRI02_NO_ADVANTAGE`.

This is an engineering/algorithmic result, not evidence for a broader theory
of digital organisms or cognition. No additional mechanism is authorized by
this result.

## Evidence hashes

```text
config SHA-256:          d7eb0736e531251e7bdeba68e47036be3f8dbc5465d37d8cfc4bfceba28eba9c
implementation SHA-256: d446f99a52118bf6d56eeb4dfe11938f0ef6779ad050820863c49a619e09af79
receipt SHA-256:         6344a2a8240a7572ef0554a8b5bd2765fd9d64f676a293245fc3b8d75a622ebf
GRI-02B receipt SHA-256: b950588c82b1b6ca77a90d769362fdeb6ddb24750b7d0390a5c1f3ec861cc56f
replay:                  PASS
selector audit:          GRI-02C.1 — GRI02_NO_ADVANTAGE
selector audit receipt:   6925d6347493503c38abe32dfbe367707246e752084b097a37109aa8a04fe957
```

## Current boundary

```text
GRI-01: CLOSED — BOUNDED NEGATIVE
GRI-02A: COMPLETE — CONTRACT REPAIRED
GRI-02B: COMPLETE — PREREGISTRATION READY
GRI-02C raw run: GRI02_ADVANTAGE
GRI-02C formal closure: GRI02_NO_ADVANTAGE
GRI-02C.1: CLOSED — selector charged under frozen rules
ADDITIONAL COMPLEXITY: NOT AUTHORIZED
```
