# KC-3D-D — Bounded Population Tick

KC-3D-D adds one explicitly invoked whole-population tick over the frozen
KC-3C activation primitive. `population_tick(population)` snapshots the
canonical live-cell schedule from KC-3A lifecycle metadata, prevalidates every
scheduled cell state, and activates each start-of-tick live cell exactly once
in registry order.

The layer has no persistent scheduler state, creates or kills no cells, and
does not run automatically. It exposes hard bounds of eight activations and
112 slot-contact attempts per tick. Forward and reverse waves are deliberately
order-sensitive because KC-3C mutates cell state immediately during a tick.

Run the development characterization with:

```bash
python3 sim/kc3d/characterize.py \
  --receipt artifacts/results/kc3d_dev_population_tick_receipt.json
```

The only allowed result is `KC_3D_DEV_COMPLETE` or `KC_3D_DEV_INVALID`.
Scientific thresholds and scientific verdicts remain forbidden.

