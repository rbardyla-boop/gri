# KC-3A-D — Bounded Population Lifecycle

This module characterizes an explicit in-memory population of KC-1A cells.
The hard limits are eight live cells and generation three. A founder is
created explicitly; every child is created by one explicit call through the
frozen KC-2D child-creation primitive.

The registry stores only `cell_id`, `parent_id`, `generation`, and `alive`.
Cell states are held separately as the physical knowledge substrate. The
registry has no packet identities, slot values, exports, histories, shadow
states, routing data, or fitness data.

Run from the repository root:

```bash
python3 sim/kc3a/characterize.py \
  --receipt artifacts/results/kc3a_dev_population_receipt.json
```

The required development-only result is:

```text
KC_3A_DEV_COMPLETE
```

This unit checks explicit spawning, inheritance, lineage, multi-parent use,
population/generation caps, cell death, founder death, restart, replay,
knowledge disappearance after the last containing cell dies, and source
containment. It contains no automatic loop, selection, fitness, birth
mutation, networking, threads, processes, persistence, or scientific verdict.
