# KC-4B-D — Capacity / Redundancy Frontier

## Claim under characterization

Under unchanged KC-3D propagation, how do deliberately frozen redundancy
profiles trade unique identities against duplicate copies, communication, and
single-cell-loss survival?

This is a development characterization. It is not a claim that KC is a
useful AI-memory architecture and it computes no scientific advantage
threshold.

## Frozen comparison

The KC condition uses the existing KC-1A state, KC-2B state export, KC-3C
local contact selection, and KC-3D population tick. The only input variation
is the frozen initial placement:

| copies per identity | unique identities | physical positions |
| ---: | ---: | ---: |
| 1 | 64 | 64 |
| 2 | 32 | 64 |
| 4 | 16 | 64 |
| 8 | 8 | 64 |

The comparison is an equally redundant static 64-address store with the same
duplicate placements and the same 1024 declared state-byte budget. It does
not receive a propagation advantage or a centralized packet map beyond its
fixed physical addresses.

For each profile the harness records the initial placement, four unchanged
KC-3D ticks, all eight cell-loss cases before the horizon, and all eight
cell-loss cases after the horizon. Every case is replayed from each of the
four restart boundaries for both conditions.

## Boundaries

The harness is characterization-only:

```text
KC-4B-D: DEV_CHARACTERIZATION_ONLY
scientific thresholds: UNDEFINED_IN_DEVELOPMENT
scientific verdict: FORBIDDEN
protocol change: false
routing: false
learning: false
selection: false
```

The required terminal states are `KC_4B_DEV_COMPLETE` and
`KC_4B_DEV_INVALID`.

## Evidence

The machine-readable receipt is:

```text
artifacts/results/kc4b_capacity_redundancy_frontier_receipt.json
```

Receipt SHA-256:

```text
a0552d5f10030a5fdcd18ead414484e86011979e23a6a6e21685056c7b23b84a
```

The frozen runner completed with `KC_4B_DEV_COMPLETE`. All 68 cases passed
anchor, schema, budget, runtime-bound, restart, replay, and non-scientific
checks. At t0 the KC profiles have exactly their declared frontier counts;
after four unchanged KC-3D ticks, every no-failure profile retained 8 unique
identities with 8 copies each:

| profile | KC t0 unique/copies | KC t4 unique/copy histogram | equal-redundancy baseline t4 |
| ---: | ---: | --- | ---: |
| r=1 | 64 / 1 | 8 / 8 identities at 8 copies | 64 |
| r=2 | 32 / 2 | 8 / 8 identities at 8 copies | 32 |
| r=4 | 16 / 4 | 8 / 8 identities at 8 copies | 16 |
| r=8 | 8 / 8 | 8 / 8 identities at 8 copies | 8 |

For the KC no-failure cases, the four-tick run used 448 slot contacts and
544 total counted operations including the 64 initial placements. The eight
before-horizon loss cases per profile retained, in C0 through C7 order:

```text
r=1: 8, 24, 24, 24, 8, 8, 8, 8
r=2: 8, 16, 16, 16, 8, 8, 8, 8
r=4: 8, 8, 16, 16, 8, 8, 8, 8
r=8: 8, 8, 8, 8, 8, 8, 8, 8
```

All after-horizon loss cases retained 8 unique identities in the KC
condition. These are exact development observations under this scheduler,
horizon, and placement bank; they are not a scientific utility verdict.
