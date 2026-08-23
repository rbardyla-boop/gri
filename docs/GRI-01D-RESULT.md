# GRI-01D — Minimal Explicit-State Control Result

**Verdict:**

```text
CONTROL_PASS
```

The deterministic finite-state transducer solved the exact corrected GRI-01
fixtures at 100% for every task and delay cell, including held-out delays 8
and 16. It also passed 418 serialize/restart continuations with byte-stable
state representation and no failures.

## Evidence

```text
config SHA-256:         9e5df90abc3daff267256a52f4d033728a030d6b651c1bc2a308d21b1ff0dc80
implementation SHA-256: 1ba152aee479bf530e6f21a4d93a2ff340d1b695b6d141393df72acd2eb80b67
receipt SHA-256:        e595b1494987c69b09ae82553d35f40d0bf3e4339b94c192816b28f75e9a7482
train cells:            9/9 at 1.0 accuracy
held-out test cells:    6/6 at 1.0 accuracy
restart continuations:  418/418 PASS
```

The control uses explicit finite registers (`memory`, `first`, `second`, and
`last_output`) and no learned parameters, lookup table, geometry, agent, or
language-model machinery.

## Interpretation

The task fixtures are valid recurrence-dependent tasks and explicit state
recurrence is sufficient to solve them. Combined with the GRI-01 result—where
the matched tanh recurrent model and stateless baseline both scored 0.5 on
held-out evaluation—this isolates the current failure more narrowly:

```text
explicit finite-state control: 100%
GRI-01 tanh recurrence:        50%
matched stateless baseline:    50%
```

This does not prove that every recurrent neural mechanism fails. It does show
that this GRI-01 formulation and frozen SGD setup did not learn the required
transition on this unit. No added complexity is authorized by the result.
