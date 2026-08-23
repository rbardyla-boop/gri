# GRI-02C.1 — Transition-Selector Accounting Audit

## Verdict

```text
FORMAL VERDICT: GRI02_NO_ADVANTAGE
ALGORITHMIC FINDING: SUPPORTED
```

This was a forensic accounting unit only. It performed no training,
evaluation, replay, architecture change, ceiling change, or result-driven
tuning.

## Finding

The frozen GRI-02B rules define a comparison as:

```text
one scalar comparison or branch predicate
```

The executable GRI-02C candidate does not receive a transition class from an
external interface. Its `forward` signature receives token ids and the
candidate branch executes:

```python
preserve = ids == self.wait_index
```

at implementation line 91. The same selector appears separately in the
`no_recurrence` ablation at line 98. The audit charges the candidate-path
selector once per active recurrent transition. It does not reopen the
pre-existing active/padding or query-framing accounting; charging those would
only increase the overrun.

## Frozen accounting

```text
                                  declared   selector   audited
preserve path                         0          +1         1
transform recurrent path             97         +1        98
transform plus query                118         +1       119

frozen parent ceilings:
transform recurrent                 97
transform plus query               118
```

Therefore the current executable candidate fails the preregistered resource
budget. The external-dispatch counterfactual would remain at 97 and 118, but
that is not the interface implemented by the frozen source and cannot be used
to authorize the result.

## Interpretation boundary

The raw GRI-02C run remains algorithmically informative: the identity-preserve
candidate reached the recorded task, precision, decoder, and ablation result.
The audit does not erase that finding. It does mean the formal preregistered
`GRI02_ADVANTAGE` condition is not met because the executable candidate’s
selector exceeds the unchanged operation ceiling.

No successor mechanism is authorized by this result.

## Evidence hashes

```text
audit source SHA-256:       8da90a325d0ea8197842438185b5bfc8ad68f4f1fa554edee5a210927ecec256
audit receipt SHA-256:       6925d6347493503c38abe32dfbe367707246e752084b097a37109aa8a04fe957
GRI-02C config SHA-256:      d7eb0736e531251e7bdeba68e47036be3f8dbc5465d37d8cfc4bfceba28eba9c
GRI-02C implementation SHA:  d446f99a52118bf6d56eeb4dfe11938f0ef6779ad050820863c49a619e09af79
GRI-02C raw receipt SHA-256: 6344a2a8240a7572ef0554a8b5bd2765fd9d64f676a293245fc3b8d75a622ebf
GRI-02B rules SHA-256:       166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3
```

## Current boundary

```text
GRI-01:   CLOSED — BOUNDED NEGATIVE
GRI-02A:  COMPLETE — CONTRACT REPAIRED
GRI-02B:  COMPLETE — PREREGISTRATION READY
GRI-02C:  ALGORITHMIC FINDING SUPPORTED; FORMAL BUDGET FAILED
GRI-02C.1 CLOSED — GRI02_NO_ADVANTAGE
SUCCESSOR / ADDITIONAL COMPLEXITY: NOT AUTHORIZED
```
