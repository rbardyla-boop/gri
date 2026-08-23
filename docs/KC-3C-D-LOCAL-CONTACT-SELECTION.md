# KC-3C-D — Local Contact Selection

## Status

```text
KC-3C-D: COMPLETE
VERDICT: KC_3C_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-3C-D layers `activate_cell(population, source_id)` over the frozen KC-3A
lifecycle and KC-3B sharing operation. The activation inspects the source
state to enumerate occupied physical slots and inspects lifecycle metadata to
derive only live parent/child neighbors. It supplies neither packet identity,
slot identity, nor target identity as an input.

The local rule shares every occupied source slot with every live lifecycle
neighbor. Linear, branching, secondary, multi-packet, dead-neighbor,
collision, duplicate, source-death, last-copy-death, restart, replay, and
immutability checks pass. The activation creates no cells and keeps zero
persistent policy state. Target knowledge is not used for policy selection;
target-state validation remains inside the frozen KC-3B delivery layer.

This is still explicitly scheduled activation. It does not establish
automatic activation, autonomous contact selection, fitness, selection,
networking, or a scientific result.

## Anchors

```text
KC-3A manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-2D child-creation source SHA-256:
f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046

KC-3B share source SHA-256:
45a1e6f76721f6e5988323276dce2defb8463dafbd491da34974263b2728b223

KC-2B export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-3C-D config SHA-256:
ea0f4a36388fbb0e5a6d250cbff489648bffa7f990eb027d4be38aa8f1c746aa

KC-3C-D activate source SHA-256:
780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d

KC-3C-D receipt SHA-256:
8a368b104024532545684fcabd3b7e1f125b6428616504ea35b44fb096fca501
```
