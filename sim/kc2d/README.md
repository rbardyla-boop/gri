# KC-2D-D — Bounded Child Creation

This module characterizes one explicit child-creation call around an
unchanged KC-1A parent. The primitive validates the parent through the frozen
KC-2B state-export interface, creates exactly one fresh KC-1A child, and
reconstructs the child from transient slot payloads. It accepts no packet
identity argument and retains no coordinator state.

Run from the repository root:

```bash
python3 sim/kc2d/characterize.py \
  --receipt artifacts/results/kc2d_dev_child_receipt.json
```

The required development-only result is:

```text
KC_2D_DEV_COMPLETE
```

The characterization covers empty, partial, and full parents, exact
inheritance, independent mutation, parent destruction, malformed and
interrupted atomic failure, restart, deterministic replay, and a bounded
G0→G1→G2 lineage. Automatic spawning, population registries, networking,
threads, processes, persistence, learning, and scientific verdicts are
forbidden.
