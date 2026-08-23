# KC-2D-D — Bounded Child Creation

## Status

```text
KC-2D-D: COMPLETE
VERDICT: KC_2D_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-2D-D characterizes one explicit `spawn_child(parent_cell, parent_state)`
call around an unchanged KC-1A parent. The primitive validates all eight
physical parent slots through the frozen KC-2B exporter, creates exactly one
fresh KC-1A child, and reconstructs its state from transient non-empty slot
payloads. The parent cell and packet identities are not supplied as separate
arguments; the child is derived from the parent’s current state.

Empty, partial, and full parents produce exact state copies. Parent and child
storage are independent: mutations do not cross the boundary, and a child
survives destruction of its parent. Malformed parents fail before child
creation. An injected mid-copy failure returns no child as an authoritative
result. Serialization/restart and a bounded G0→G1→G2 lineage are
deterministic.

The resource boundary is explicit: one child per call, zero automatic spawn
calls, zero coordinator state, no population registry, and no filesystem,
network, thread, process, timer, scheduler, or replication machinery. This is
bounded child creation, not a population or scientific result.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-2B export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-2D-D config SHA-256:
9a961d621ae6ffc485746d1738df67d2785f4083732a3d9bdbf57d43e96b6db0

KC-2D-D spawn source SHA-256:
f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046

KC-2D-D receipt SHA-256:
f38770e8e8cff95e6f58273dc2a1349f39d912fe620d96a60c7aaa7d9dcabae1
```

The receipt’s canonical internal digest is
`e919fef5a55bee4d6c063b42d74496354a792b23766dd689ed7f5ce6d508fc9c`.
