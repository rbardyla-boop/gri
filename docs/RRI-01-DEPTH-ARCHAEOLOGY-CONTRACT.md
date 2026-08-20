# RRI-01 — Depth-Failure Archaeology

Status: PREREGISTERED / OBSERVATIONAL ONLY

RRI-01 consumes only the five frozen GRI-05 baseline checkpoints. It performs
no training, creates no optimizer, calls no update operation, and must leave
every model tensor unchanged.

## Frozen inputs and execution

- Checkpoints: `artifacts/rri01r/checkpoints/baseline_seed{1337,1338,1339,1340,1341}_final.pt`.
- Inputs: frozen WORLD-0 `test_iid`, `test_depth_5`, `test_depth_8`, `test_depth_16`, `test_depth_32`, and `test_depth_64`.
- Recurrent steps: every integer `1..128`.
- Gradient diagnostics: steps `1,2,4,8,16,32,64,128`; gradients are with respect to initial hidden state only and never update parameters.
- Trace equivalence: ordinary frozen forward and traced forward at `1,2,4,8,16,32,64`, tolerance `1e-6` absolute/relative.

## Fixed statistics

- State residuals: mean node L2 absolute and relative movement; mean, minimum,
  and maximum node norm.
- Oversmoothing: mean off-diagonal node cosine similarity and mean feature
  variance across nodes.
- Relation retention: `z = concat(h_subject, h_object, h_subject-h_object)`.
  `between` is the mean squared distance of class centroids from the global
  centroid; `within` is the mean squared distance from each sample to its
  class centroid; `SEP = between / (within + 1e-12)`.
- Temporal similarity: cosine similarity of flattened states at lags `1,2,4,8`.
- Primary accuracy diagnostics use the existing frozen readout, with true-label
  probability, predicted-label probability, logit margin, entropy, first and
  last correct steps, transitions, longest correct run, and stable-correct step.

## Frozen failure signatures

- Overthinking/state erosion: aggregate accuracy reaches a peak, later falls by
  at least `.20`, and at least 25% of long-chain samples have a correct-to-wrong
  transition after first becoming correct.
- Oversmoothing: cosine reaches `.90`, dispersion falls at least 50% from the
  step-1 reference, and the change overlaps a `.20` accuracy degradation.
- Update stall: median relative residual is below `1e-3` before resolution for
  at least 25% of long-chain samples, which remain incorrect for at least 16
  subsequent steps.
- Dynamical instability: non-finite states, or hidden norm/residual at least
  10x its step-1 reference.
- Relation erasure: SEP falls at least 50% from its peak with concurrent `.20`
  accuracy degradation, unless oversmoothing is the more direct signature.
- Readout mismatch: accuracy falls `.20` from peak while SEP retains at least
  80% of its peak.
- Gradient/influence decay: mean initial-state gradient norm falls at least
  100x from its earliest selected-step reference while long-depth accuracy
  degrades by `.20`.

A primary diagnosis requires the same signature in at least 4/5 seeds.
Otherwise the terminal diagnosis is `RRI_01_FAILURE_MODE_UNRESOLVED`.

## Required evidence

The runner writes per-seed JSONL traces, summaries, aggregate statistics,
diagnosis, report, and SHA-256 manifest under `artifacts/rri01/`. The
instrumentation commit must precede all generated evidence.
