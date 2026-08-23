# GRI-SC-1L — Learnability Grid Result

**Status:** `DEV_LEARNABILITY_ONLY`

## Bounded result

The fixed SC-1L grid produced:

```text
LEARNABILITY_SIGNAL
```

This is a development signal only. It is not a scientific verdict, does not
freeze Candidate B, and does not authorize SC-2.

The runner's declared development criterion was met when one fixed
optimizer/learning-rate configuration reached 100% fit, held-out, and all
fixture accuracy for all three preregistered seeds, with passing restart smoke.
Both `SGD lr=0.1` and `Adam lr=0.003` met that criterion.

## Frozen execution

The run used the immutable Candidate B source and manifest, the frozen GRI-02B
fixtures and operation rules, fit data only for optimization, seeds
`20260820`, `20260821`, and `20260822`, and a 400-epoch cap.

```text
SGD:  0.003, 0.01, 0.03, 0.1
Adam: 0.0003, 0.001, 0.003
Runs: 21
Restart smoke: first 32 fixtures per run
Scientific verdict: FORBIDDEN
Candidate freeze: false
Scientific run: false
```

Per-run fit/held-out/all accuracies are recorded in the machine-readable
receipt. All 21 restart checks passed. The post-training fixed-decoder
diagnostic found a separator for every task in every run, with 100% held-out
diagnostic accuracy; this does not replace the model-readout training metric.

The separate deterministic float64 LBFGS diagnostic, capped at 100 iterations
and started from `0`, `1`, and `2`, remained analysis-only and returned
`REPRESENTABLE`.

## Anchors and receipts

```text
Candidate B source:
64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218

Candidate B manifest:
f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584

Fixture bank:
f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960

Operation rules:
166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3

SC-1L authorization:
25142cc2d044d3d07c1459ea9e345d6c2f87141876c6ac8588c8149d420712d4

Learnability-grid receipt:
b91a3fd10e3df7a1f24f301bd199a1d27b3938720f0fc8a635de51fb476df0af

LBFGS diagnostic receipt:
efdce8201193e52931cbbc88c703c2a199ebcfc5cef0b178c13aa22251e831bc
```

## Canonical boundary

```text
REPRESENTABLE: YES
IN-BUDGET: YES
BRANCH-FREE: YES
DEVELOPMENT LEARNABILITY SIGNAL: YES
SCIENTIFIC ADVANTAGE: NOT ESTABLISHED
MINIMALITY: NOT ESTABLISHED
SC-2: NOT AUTHORIZED
```

No architecture, fixture, budget, interface, or scientific artifact was
changed by this unit.
