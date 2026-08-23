# GRI-01F — Recurrent State Stability / Memory Half-Life

**Verdict:**

```text
CONTRACTIVE_MEMORY
```

The exact deterministic d=8 GRI-01E solution was reused without retraining.
Each required state pair was initialized from the same task prefixes and then
advanced only by the frozen `WAIT` transition through 128 steps.

## Evidence

```text
config SHA-256:         53a430d6053e07e8b84e0b6692baf4f50a4858fdb8964ddb4462557b09f249bc
implementation SHA-256: fa46d2dcf79a61ebdcc29a5d1f28754d3d3de00070c5664e6c84214d529c381c
receipt SHA-256:        a5ebc794b53c80a7002ba8c5ca09ffa83448aeab6d89eb3b5dd604e0e336a894
replay:                 PASS
```

| Required distinction | Initial separation | Final separation ratio | First prediction failure |
|---|---:|---:|---:|
| delayed bit | 4.4688 | 0.0000 | WAIT 0 |
| correction | 2.6535 | 0.0000 | WAIT 0 |
| order | 5.0500 | 0.0000 | WAIT 3 |

All three pairs reached the same hidden state by the end of the horizon. The
explicit finite-state control preserves its relevant distinction across the
same horizon. The recorded local Jacobian spectral radii can exceed 1 along
parts of the nonlinear trajectory, but the observed trajectories still merge;
the verdict is based on the measured state separation and readout failures.

## Interpretation

The current GRI-01 d=8 solution does not have protected state invariants. Its
failure is now localized from “did not learn the task” to “the learned state
representation is erased by the repeated no-op transition.” This supports a
more precise future hypothesis about recurrence: preservation steps may need a
separate invariant-state mechanism. That mechanism is not added here and is
not authorized by this result.
