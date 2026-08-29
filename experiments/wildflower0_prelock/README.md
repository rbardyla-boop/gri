# WILDFLOWER-0 pre-lock engineering shakeout

Status: **experimental branch; architecture not frozen**.

This package tests a minimal world-first, tokenizer-free seed using only numeric sensor arrays and machine action IDs. It intentionally runs hostile engineering checks before any architecture is promoted.

Current components:

- visual encoder from random initialization;
- raw waveform encoder from random initialization;
- shared semantic + private visual-state representation;
- audiovisual alignment without transcripts or text labels;
- self-supervised visual reconstruction;
- latent action dynamics;
- append-only hash-chained episodic history with bounded active memory;
- direct pixel-dynamics alternative;
- observation-corrected recurrent multi-horizon alternative;
- deterministic replay/static dependency checks;
- trivial baseline comparisons;
- sequential forgetting and open-loop compounding tests.

Run the main shakeout:

```bash
PYTHONPATH=. python -m compileall -q wildflower0 tests run_shakeout.py run_variant_probe.py run_recurrent_probe.py
PYTHONPATH=. python -m pytest -q -W error
PYTHONPATH=. python run_shakeout.py --seeds 4 --train-steps 180
```

Run the materially different pixel-dynamics probe:

```bash
PYTHONPATH=. python run_variant_probe.py
```

Run the recurrent/multi-horizon failure probe:

```bash
PYTHONPATH=. python run_recurrent_probe.py
```

The current pre-lock verdict is **FAIL / CONTINUE ENGINEERING**. Bounded replay repairs the observed continual-forgetting failure, while the transition architecture remains unresolved: latent dynamics loses to a trivial one-step copy baseline; direct pixel dynamics beats that baseline but accumulates large open-loop rollout error; the first recurrent multi-horizon repair suppresses error growth only by collapsing into a poor predictor that loses simple controls.

See `PRELOCK_FINDINGS.md` and `evidence/` for preserved receipts.

A passing engineering gate would still not establish grounded language, AGI, novelty, or superiority on a recognized external benchmark.
