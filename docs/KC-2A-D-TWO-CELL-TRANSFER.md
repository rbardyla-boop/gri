# KC-2A-D — Two-Cell Knowledge Transfer

## Status

```text
KC-2A-D: COMPLETE
VERDICT: KC_2A_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-2A-D uses two unchanged KC-1A instances with separate persistent state.
The transfer adapter receives a source state and a requested packet token,
creates only a transient token payload, and delivers it through the unchanged
destination cell. The coordinator declares zero persistent state bytes.

The characterization passes isolation, exact transfer, duplicate delivery,
occupied-slot collision routing, restart during transfer, distributed load,
source-loss survival, destination-loss-before-transfer, and deterministic
replay. The two-cell load recovers 16 current packet identities: eight in each
cell. A source cell can be discarded after transfer while the destination
retains the packet.

The transfer adapter also receives a source-structure audit. It has no class
definition or global statement and no forbidden history, shadow-table,
population, or replication identifiers. This audit is a containment check,
not a proof against arbitrary interpreter-level tampering.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-2A-D config SHA-256:
2997f22119e55001ad81e1225df427876b5bdb94b7e0ae23870eb742256d59fd

KC-2A-D transfer source SHA-256:
d5268e31af73822c5e86acded3b579054114d58f9f05c86e32ce5b404a17c6d6

KC-2A-D receipt SHA-256:
9a7035f7014a9aef13cf1f204bc31fab3d5882a1028eef6672b8dc5b14483458
```

The receipt’s canonical internal digest is
`e9cd3807b69a1bbef09e25ad70af0d0a44965f019c7699fff72bb8ac8532383a`.

## Boundary

This is a lifecycle and interface characterization only. It does not claim
that transfer is useful knowledge retention, that cells learn, that cells
replicate, or that a population can emerge. Replication and population logic
remain unimplemented and unauthorized.
