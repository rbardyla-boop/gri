# KC-2C-D — Cooperative Overflow Preservation

This module characterizes a stateless two-cell protocol around two unchanged
KC-1A cells. Incoming tokens are written to Cell A. When the incoming token
would overwrite a different value in A's physical slot, the protocol exports
the displaced value using the frozen KC-2B adapter, delivers it to Cell B,
and then writes the incoming token to A.

Run from the repository root:

```bash
python3 sim/kc2c/characterize.py \
  --receipt artifacts/results/kc2c_dev_overflow_receipt.json
```

The required development-only result is:

```text
KC_2C_DEV_COMPLETE
```

The characterization covers single overflow, a collision-heavy 16-packet
stream, pair saturation, concentrated same-slot recency, duplicate and
already-held inputs, different-slot traffic, malformed states, restart,
replay, cell-loss consequences, zero coordinator state, and a source audit.
It does not implement reproduction or population logic and emits no
scientific verdict.
