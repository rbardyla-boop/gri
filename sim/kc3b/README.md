# KC-3B-D — Bounded Knowledge Spread

This module characterizes explicit local slot sharing over the frozen KC-3A
population lifecycle. The population is built first; a packet is then
introduced into one existing cell. `share_slot(population, source_id,
target_id, slot_id)` derives a transient payload from source state through
the frozen KC-2B exporter and consumes it in the target cell.

The share interface accepts only population, source ID, target ID, and
physical slot. It returns only whether a non-empty slot was delivered. It
does not accept or expose a packet identity, expected value, knowledge list,
fixture identity, or query metadata, and it creates no cells.

Run from the repository root:

```bash
python3 sim/kc3b/characterize.py \
  --receipt artifacts/results/kc3b_dev_spread_receipt.json
```

The required development-only result is:

```text
KC_3B_DEV_COMPLETE
```

The characterization covers post-birth acquisition, one-hop and multi-hop
spread, secondary forwarding, branching, source and last-copy death, empty
and wrong slots, same-slot collision, duplicate contacts, contact order,
restart/replay, unchanged lifecycle metadata/caps, registry containment, and
absence of automatic contacts. It does not implement autonomous propagation,
fitness, selection, mutation, networking, or scientific verdicts.
