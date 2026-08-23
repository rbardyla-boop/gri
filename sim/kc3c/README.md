# KC-3C-D — Local Contact Selection

This module characterizes explicit activation of one live KC-3A cell. The
interface is only `activate_cell(population, source_id)`. The activation
derives occupied source slots from source state and derives live parent/child
neighbors from lifecycle metadata. It then delegates slot delivery to the
frozen KC-3B sharing operation.

The policy does not receive packet, slot, or target IDs from the harness and
does not inspect target state to choose contacts. It holds no cursor, queue,
sent-set, routing table, knowledge map, or persistent policy state. Each
activation remains an explicit harness call and creates no cells.

Run from the repository root:

```bash
python3 sim/kc3c/characterize.py \
  --receipt artifacts/results/kc3c_dev_activation_receipt.json
```

The required development-only result is:

```text
KC_3C_DEV_COMPLETE
```

The characterization covers post-birth acquisition, linear and branching
waves, secondary propagation, dead neighbors, empty/partial/multi-packet
sources, collisions, duplicate activation, source and last-copy death,
restart/replay, lifecycle/population immutability, and the zero-policy-state
audit. Automatic activation, automatic contacts, selection, networking, and
scientific verdicts are forbidden.
