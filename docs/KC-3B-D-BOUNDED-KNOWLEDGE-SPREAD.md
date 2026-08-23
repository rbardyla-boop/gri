# KC-3B-D — Bounded Knowledge Spread

## Status

```text
KC-3B-D: COMPLETE
VERDICT: KC_3B_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-3B-D layers an explicit stateless `share_slot(population, source_id,
target_id, slot_id)` operation over the frozen KC-3A manager. It exports the
requested physical source slot through the frozen KC-2B adapter and, when
non-empty, delivers the transient payload by the unchanged KC-3A consume
operation. Sharing creates no cells and does not mutate the lifecycle
registry.

The population is constructed before the packet is introduced. The
characterization passes one-hop, multi-hop, secondary forwarding, branching,
source death, last-copy death, empty/wrong-slot behavior, same-slot collision,
duplicate contact, explicit contact order, mid-spread restart, deterministic
replay, population/generation preservation, and registry containment. The
registry remains exactly `cell_id`, `parent_id`, `generation`, and `alive`.

This establishes only scheduled local propagation in a bounded simulator. It
does not establish autonomous contact selection, automatic propagation,
fitness, selection, mutation, networking, or a scientific result.

## Anchors

```text
KC-3A manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-2D child-creation source SHA-256:
f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046

KC-2B export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-3B-D config SHA-256:
eda0e4ec0dee04590f85073400193066f6955cff11320c5bd3cf41e5c9d8934b

KC-3B-D share source SHA-256:
45a1e6f76721f6e5988323276dce2defb8463dafbd491da34974263b2728b223

KC-3B-D receipt SHA-256:
ed86bfcfbbde7b47688b32da415d2c2eb943978ecaa8fba587d21799e2302ad2
```

The receipt’s canonical internal digest is
`7fd8e6829fb3e8499accb446429dfeb13f333cb6f70a75c6cf6126b4ba023653`.
