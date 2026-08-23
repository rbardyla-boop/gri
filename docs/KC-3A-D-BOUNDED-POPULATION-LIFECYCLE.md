# KC-3A-D — Bounded Population Lifecycle

## Status

```text
KC-3A-D: COMPLETE
VERDICT: KC_3A_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-3A-D introduces the first lifecycle registry, with a deliberately relaxed
resource boundary. The registry may store only `cell_id`, `parent_id`,
`generation`, and `alive`. Knowledge remains in live KC-1A cell states, which
are stored separately from lifecycle metadata.

The population is capped at eight live cells and generation three. Founders,
spawns, consumption, and death are explicit harness operations. Every child
is created through the unchanged KC-2D child-creation primitive. Population
and generation caps fail closed; serialization/restart reconstructs live
cells and lifecycle metadata; and deterministic replay reproduces registry
and state hashes.

The containment negative control passes: after the last cell containing a
packet is explicitly killed, no live state payload remains and the registry
cannot reconstruct that packet. There is no automatic spawning, fitness,
selection, mutation at birth, network, filesystem persistence, thread,
process, timer, scheduler, or population-level knowledge store.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-2B export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-2D child-creation source SHA-256:
f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-3A-D config SHA-256:
ddbfc6155f248c227503acf9504b0789874e89a6dc446f4d5369ec9162cb8b5f

KC-3A-D manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-3A-D receipt SHA-256:
0368efbd8415752458b287c730709489b9db71d86ba31920e95f09836e5e5aa8
```

The receipt’s canonical internal digest is
`4369ebd44978bcba76c6040b4736590920e0a8199c4fffe05ce3191c2613c6fd`.
