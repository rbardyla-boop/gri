# GRI-01 — Smallest Recurrence Unit Result

**Run status:** COMPLETE for the repaired fixture; no tuning was performed
after the corrected run.

## Verdict

```text
NO_ADVANTAGE
```

Under the frozen minimal unit, the recurrent primitive did not outperform the
matched stateless baseline on held-out delays. This is a bounded result for
this unit and parameterization, not a verdict on every possible GRI model.

## Frozen execution

```text
config SHA-256:         9e5df90abc3daff267256a52f4d033728a030d6b651c1bc2a308d21b1ff0dc80
implementation SHA-256: d8182c2bb07d3b4ddf93e951c3cd6ca43ec10208ad63a0b0f8d9b3e51ac15f37
receipt SHA-256:        13697874094e48fd65b019c89389b79cf37b537aaecb52a7b663b9e22d827687
dimensions:             2, 4, 8
seeds:                  1337, 1338, 1339
train delays:           1, 2, 4
held-out delays:        8, 16
```

All nine recurrent and stateless parameter counts matched exactly: 32, 70,
and 170 for dimensions 2, 4, and 8. Every corrected-run held-out accuracy was
0.5 for the recurrent model, reset ablation, and stateless baseline. The
deterministic replay produced the same receipt contents after excluding only
the run timestamp.

## Interpretation

The stateless baseline performed equivalently to the recurrent primitive on
this run, so the predeclared rule returns `NO_ADVANTAGE`. No extra memory,
geometry, agent machinery, language model, or human experiment is authorized
by this result.

The first attempted run is preserved as
`artifacts/results/gri01_recurrence_receipt_run1_inconclusive.json`; it is not
scientific evidence because correction/order examples were incorrectly labeled
with held-out delays without containing those delays. That fixture-construction
bug was repaired before the reported run, with the same hyperparameters and
verdict thresholds.
