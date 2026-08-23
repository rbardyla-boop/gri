# KC-2B-D — Oracle-Free State Export

This module is a development-only characterization of exporting stored
packet identities from an unchanged KC-1A state without supplying the packet
identity to the export interface.

The adapter accepts only a source state and a physical slot index. It derives
the packet from the slot’s stored value and occupancy bit, returns `None` for
an empty slot, and fails closed for malformed or slot-inconsistent state. A
transient export payload can be delivered to another unchanged KC-1A cell;
the adapter retains no history or persistent payload state.

Run from the repository root:

```bash
python3 sim/kc2b/characterize.py \
  --receipt artifacts/results/kc2b_dev_export_receipt.json
```

The required development-only result is:

```text
KC_2B_DEV_COMPLETE
```

This unit checks empty and wrong-slot requests, exact single export, malformed
state rejection, full eight-slot export, source destruction, interruption
restart, destination loss before transfer, interface/source audits, zero-byte
coordinator state, and deterministic replay. It establishes no replication,
population, learning, retention threshold, or scientific verdict.
