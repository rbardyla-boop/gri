# KC-2A-D — Two-Cell Knowledge Transfer

This module is a development-only characterization of an explicit transfer
interface between two unchanged KC-1A cells.

The cells have independent persistent state. The adapter exposes only a
transient packet token: it does not retain packet history, a shadow slot
table, global memory, population state, or replication logic. Its declared
coordinator state is zero bytes.

Run the characterization from the repository root:

```bash
python3 sim/kc2a/characterize.py \
  --receipt artifacts/results/kc2a_dev_transfer_receipt.json
```

The required development-only result is:

```text
KC_2A_DEV_COMPLETE
```

This unit checks isolation, explicit transfer, duplicate delivery, occupied
slot collision behavior, transfer-time restart, distributed 16-item load,
source/destination loss boundaries, deterministic replay, and a static audit
of the transfer adapter. It establishes no replication, population, learning,
retention threshold, or scientific verdict.
