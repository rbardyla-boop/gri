# GRI-SC-1R.1 — Branch-Free Counterexample Accounting Audit

## Verdict

```text
AUDIT: PASS
COUNTEREXAMPLE: ADMISSIBLE
SELECTOR_COST_LOWER_BOUND: DISPROVED BY CONSTRUCTION
SCIENTIFIC VERDICT: FORBIDDEN
```

This was a forensic audit only. It performed no training, optimization,
candidate modification, candidate freeze, or scientific run.

## Runtime audit

Candidate B’s runtime `step()` is source lines 38–42:

```python
embedded = self.input(token_ids)
transformed = torch.tanh(state * self.diagonal + embedded)
residual = transformed - state
return state + embedded[:, :1] * residual
```

The line-level AST audit found:

```text
step comparisons:       none
step branches:          none
forbidden metadata:     none
```

The simulator’s one comparison and one branch are both constructor-time
`state_width` validation at line 21. The `wait_index` use at lines 27–33
initializes the fixed semantic embedding coordinate and the training-time
gradient mask; neither runs in the recurrent transition.

The runtime checks confirmed:

```text
fixed semantic code:     exact 0/1 values
WAIT transition:         exact identity
event transition:        changes the sample state
```

The candidate receives token IDs only through the existing embedding lookup.
It receives no fixture id, label, task, delay, sequence position, query
horizon, or other metadata.

## Operation accounting

| Runtime component | Operations |
|---|---:|
| Token lookup | 1 |
| Embedding scalar copies | 8 |
| Diagonal state multiplication | 8 |
| State + embedding | 8 |
| `tanh` | 8 |
| Residual subtraction | 8 |
| Semantic residual multiplication | 8 |
| Residual state addition | 8 |
| **Recurrent total** | **57** |
| Query readout | 21 |
| **Recurrent + query** | **78** |

The existing embedding copies already include the reused first semantic
coordinate; `embedded[:, :1]` is a view, not a comparison or dispatch. Even a
conservative extra scalar-copy charge would leave the recurrent total at 58,
still below the frozen ceiling of 97.

Parameter and state accounting also passes:

```text
embedding:             80 slots
fixed semantic code:   10 slots
trainable embedding:   70 slots
diagonal:               8 slots
readout:               18 slots
trainable total:       96
persistent state:       8
```

## Formal consequence

The audit closes the original SC-0 question under the frozen model:

```text
TOKEN-CLASS DEPENDENCE:
    NECESSARY

EXTRA EXPLICIT SELECTOR OPERATION:
    NOT NECESSARY UNDER THE FROZEN MODEL

SELECTOR-COST LOWER BOUND:
    DISPROVED BY CONSTRUCTION
```

This does not establish scientific advantage, general learnability, or
minimality. The earlier SGD smoke failure remains a learning/search failure;
the deterministic SC-1R solver established representability, and this audit
established admissibility.

## Evidence hashes

```text
Candidate B source SHA-256:
64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218

Candidate B manifest SHA-256:
f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584

SC-1R representability receipt SHA-256:
efdce8201193e52931cbbc88c703c2a199ebcfc5cef0b178c13aa22251e831bc

Audit source SHA-256:
746b7e19009d96116d522c0ecf0e76d4fafed54f8955258a75e25ab8024db1b8

Audit receipt SHA-256:
50e35bff74a0918342ee58b339bfc74e9dfb7f6462f59a302eff79335706135e
```

## Current boundary

```text
GRI-SC-0:   SELECTOR-COST LOWER BOUND DISPROVED BY CONSTRUCTION
GRI-SC-1:   DEV_SMOKE COMPLETE
GRI-SC-1R:  REPRESENTABLE
GRI-SC-1R.1: CLOSED — ACCOUNTING AUDIT PASS
GRI-SC-2:   NOT AUTHORIZED
SCIENTIFIC LEDGER: UNCHANGED
SUCCESSOR: NOT AUTHORIZED
```
