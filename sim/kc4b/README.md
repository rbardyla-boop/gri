# KC-4B-D — Capacity / Redundancy Frontier

KC-4B-D is a development-only characterization of the frozen KC-3D
population under four explicit placement profiles: one, two, four, or eight
copies of each packet identity. It does not change KC-1A, KC-2B export,
KC-3C contact selection, or KC-3D tick behavior.

Each profile occupies the same 64 physical positions and 1024 declared state
bytes. The harness compares the KC population with an equally redundant,
static 64-address baseline, executes four explicit KC-3D ticks, and applies
every single-cell loss before and after the horizon. It records unique
identities retained, copies per identity, occupied positions, utilization,
contacts, operations, restart, and replay.

This unit characterizes the capacity/redundancy frontier only. It does not
add routing, collision resolution, learning, selection, population logic, or
a scientific threshold/verdict.

Run:

```bash
python3 sim/kc4b/benchmark.py \
  --receipt artifacts/results/kc4b_capacity_redundancy_frontier_receipt.json
```

The only permitted terminal states are `KC_4B_DEV_COMPLETE` and
`KC_4B_DEV_INVALID`.
