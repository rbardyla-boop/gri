# GRI-01G — WAIT Semantics / Transient-Coding Diagnostic

**Verdict:**

```text
TRANSIENT_CODING
```

The exact d=8 GRI-01E solution was reused without retraining and evaluated at
every wait count from 0 through 32. The identity counterfactual changed only
the `WAIT` update to `h_next = h`; query transitions remained unchanged.

## Observed correctness windows

| Task | Normal WAIT success | Identity-WAIT result |
|---|---|---|
| delayed bit | 1–5: 1.0; 0 and 6–32: 0.5 | 0.5 at every wait |
| correction | 1, 2, 4: 1.0; 3 and 6: 0.75; 0 and 5–32: 0.5 | 0.5 at every wait |
| order | 0, 1, 2, 4: 1.0; 3 and 7–32: 0.5; 5–6: 0.0 | 1.0 at every wait |

The full machine-readable matrix is in the receipt.

## Evidence

```text
config SHA-256:         0abd1700df55a405e38c8631ed98616da19ecf4b6ebade89ffa74b1dbefe4b30
implementation SHA-256: 0017494ec8b8b9235727c9da5a8d86d6e49c9c20ef8f1f3413552612bee7355d
receipt SHA-256:        d1dc6936acceee94ae6d272998774aabe70bd4d1fab9c799ae97a90a971c2335
replay:                 PASS
```

## Interpretation

The result supports transient/phase coding rather than durable semantic
state. Normal `WAIT` sometimes moves the hidden state through a readable
trajectory; identity `WAIT` does not recover delayed-bit or correction memory.
Order is an exception because its prefix state remains readable under the
identity counterfactual, so the result is not a claim that every task uses the
same coding mechanism.

The current GRI-01 cell therefore has no explicit preserve/transform
distinction: even a semantic no-op is an active nonlinear update. No protected
memory mechanism is added by this experiment.
