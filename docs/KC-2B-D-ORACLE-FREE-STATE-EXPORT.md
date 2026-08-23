# KC-2B-D — Oracle-Free State Export

## Status

```text
KC-2B-D: COMPLETE
VERDICT: KC_2B_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

KC-2B-D keeps KC-1A unchanged and tests whether a source cell can expose a
stored packet from its own state using only a physical slot index. The export
adapter does not receive a packet identity, expected value, fixture identity,
query identity, history, or external knowledge table. It derives the packet
from the stored value and occupancy bit and fails closed when those fields are
inconsistent.

The characterization passes empty-slot and wrong-slot requests, exact single
export, malformed-state rejection, full eight-slot export, exact whole-state
copy, source destruction, interruption during export with serialization and
restart, destination loss before transfer, deterministic replay, and a static
interface/source audit. The full eight-slot copy recovers the same canonical
KC-1A state in the destination after the source is discarded. The coordinator
declares zero persistent state bytes.

This is still export/copy, not replication. The destination cell is supplied
by the simulator, and no cell creates a child or population. No learning,
retention threshold, or scientific verdict is assigned.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

KC-2B-D config SHA-256:
ad68f96d789d07471b33f3a2cdbae201c510226ea1a536ca8e7c69c52f0d22ed

KC-2B-D export source SHA-256:
e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264

KC-2B-D receipt SHA-256:
e0515f53d77b5042a60faba7d581239480a00eb11e3f76711630b095660a14a0
```

The receipt’s canonical internal digest is
`2830b538e74d29a89ed53cb596f94a241995d16522d5d99961e17d441741c096`.
