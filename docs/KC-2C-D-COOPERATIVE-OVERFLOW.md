# KC-2C-D — Cooperative Overflow Preservation

## Status

```text
KC-2C-D: COMPLETE
VERDICT: KC_2C_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-2C-D characterizes a stateless overflow protocol over two unchanged
KC-1A cells. The incoming token identifies its physical slot. If Cell A's
slot is empty or already contains that token, A consumes the input directly.
If the slot contains a different value, the protocol exports A's displaced
value through the frozen KC-2B state-export interface, delivers it to Cell B,
and then writes the incoming token to A.

The collision-heavy stream sends eight first-wave packets followed by eight
new packets at the same physical addresses. The pair recovers 16 current
identities without pre-dividing the stream between cells. A third value at one
address demonstrates the bounded two-deep recency behavior: the newest value
is in A, the previous value is in B, and the oldest value is lost. Duplicate
inputs, already-held inputs, different-slot traffic, malformed states,
mid-stream restart, deterministic replay, and loss of either cell are also
characterized.

The coordinator declares zero persistent state bytes and has no packet
history, queue, timestamp, routing table, shadow state, population state, or
replication logic. This is cooperative capacity characterization, not
replication: the simulator still supplies both cells and their lifecycle.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-2B export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-2C-D config SHA-256:
8d5e56b804800d2da35957851bef117afdb33f9986d275b6f5f5a856b4e99ed1

KC-2C-D protocol source SHA-256:
f7c50f104578716d5780a63a5ff039c5ccc3a75603443d990e3f981a409d6f51

KC-2C-D receipt SHA-256:
bae80f1f0f0a75acc9614b83398fd9ef4a7da670d87964d21d7be1f5ffc06dcb
```

The receipt’s canonical internal digest is
`9e1fe6d6989437d64295e959f6a137c2d61a0b1d2814a44415c48c8940a43ef5`.
