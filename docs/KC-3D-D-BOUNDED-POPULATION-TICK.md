# KC-3D-D — Bounded Population Tick

## Status

```text
KC-3D-D: COMPLETE
VERDICT: KC_3D_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-3D-D adds one explicitly invoked `population_tick(population)` call over
the frozen KC-3C activation primitive. At tick start it derives the canonical
live-cell schedule from KC-3A lifecycle metadata, prevalidates every scheduled
KC-1A state, and activates each start-of-tick live cell exactly once in
registry order.

The characterization covers forward and reverse order-sensitive cascades,
within-tick secondary forwarding, branching, multi-packet state, dead-cell
exclusion, same-slot collision consequences, repeated stable ticks,
between-tick serialization/restart, malformed-state fail-closed preflight,
registry/population/generation immutability, deterministic replay, and the
maximum eight-activation/112-slot-contact case. The tick holds zero persistent
scheduler state and creates or kills no cells.

This remains an explicit simulator call, not a background process or an
automatic population loop. It establishes no fitness, selection, learning,
networking, reproduction, or scientific result.

## Anchors

```text
KC-3A manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-3B share source SHA-256:
45a1e6f76721f6e5988323276dce2defb8463dafbd491da34974263b2728b223

KC-3C activation source SHA-256:
780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d

KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-3D-D config SHA-256:
0eeb04cf496d4bd77c5a1ecf9e81286bc57a8508daa9577eb929694fef2bbb6e

KC-3D-D tick source SHA-256:
290ad31ad658318f10e14a39aa0be6a7de684d8f527061447a44ed4fa7bf5502

KC-3D-D receipt SHA-256:
e7c84b7125d3d698b1bc125582ef3929a5416957cf217e21d5f94980b02eb077
```
