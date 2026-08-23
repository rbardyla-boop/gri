# KC-3F-D — Scheduler Counterfactual

## Status

```text
KC-3F-D: COMPLETE
VERDICT: KC_3F_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-3F-D is a development-only counterfactual harness beside frozen KC-3D.
The KC-3D canonical `population_tick()` remains the reference condition. The
harness uses the unchanged KC-3C `activate_cell()` primitive and compares four
fixed start-of-tick orders derived only from lifecycle cell IDs:

```text
ascending   C0 C1 C2 C3 ...
descending  ... C3 C2 C1 C0
even_odd    even numeric IDs, then odd numeric IDs
odd_even    odd numeric IDs, then even numeric IDs
```

For every condition it records complete `t0`–`t4` trajectories, final packet
identities and copy counts, ticks-to-full-distribution where applicable,
observed fixed/repeat labels, population digests, restart from every boundary,
and deterministic replay. The canonical ascending condition matches frozen
KC-3D for every scenario and all four counterfactual orders begin from
byte-identical initial populations.

The same-slot control is recorded as scheduler/contact-order behavior, not
fitness or selection. In the tested placement, the final identity changes with
order; this is a bounded development observation, not a general population
law. No random or adaptive ordering, optimization, spawning, background
execution, scientific threshold, or scientific verdict is present.

## Anchors

```text
KC-3D population-tick source SHA-256:
290ad31ad658318f10e14a39aa0be6a7de684d8f527061447a44ed4fa7bf5502

KC-3D config SHA-256:
0eeb04cf496d4bd77c5a1ecf9e81286bc57a8508daa9577eb929694fef2bbb6e

KC-3E characterization source SHA-256:
797f089a9b696a16a08309cbd164cbc6af1646d14fa3ffc05d41c00dadd668be

KC-3C activation source SHA-256:
780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d

KC-3A manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-3F-D config SHA-256:
a413e273ece98d0f4f69edad87598b749668da8a2c46c6385120b19dffab033c

KC-3F-D characterization source SHA-256:
4d041835be734cfcca1d86ee908c0bae35de19f4467a2529361b96cf799be7e3

KC-3F-D receipt SHA-256:
ee2b6c7ad536dc0577100a0927962ac1a4195da004ad7f884d00825d864fbde5
```
