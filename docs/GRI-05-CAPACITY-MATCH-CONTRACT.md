# GRI-05 — Capacity-Matched SO(4) Comparison Contract

Status: PREREGISTERED / NO RESULT
Parent benchmark: frozen WORLD-0 at `1200050d1bbe99a7158e8482dacc534feb48d4c1`.

## Claim under test

Whether the current SO(4) model provides a learning or extrapolation advantage over the weight-tied recurrent graph baseline on frozen WORLD-0 when trainable parameter count, optimizer, training budget, data, and seeds are matched.

## Frozen model pair

- Baseline: `hidden_dim=49`, `message_dim=51`.
- SO(4): `semantic_dim=39`, `channels=2`, `message_dim=44`.
- Both contain exactly **30,912 trainable parameters**.

No dummy or frozen padding parameters are permitted.

## Frozen training protocol

- epochs: 80
- recurrent training steps: 4
- batch size: 16
- optimizer: AdamW
- learning rate: 0.003
- weight decay: 0.0001
- gradient clipping: 1.0
- deterministic seeds: 1337, 1338, 1339, 1340, 1341
- PyTorch CPU threads: 1

The same seed controls model initialization and training order.

## Evaluation

Report train accuracy, IID validation accuracy, and accuracy at exact extrapolation depths 5, 8, 16, 32, and 64.

Primary metric:

`P = mean(D8, D16, D32, D64)`

Depth 5 is diagnostic and is not part of the primary metric.

## Advance rule

SO(4) advances only if all conditions hold across the five preregistered seeds:

1. mean SO(4) train accuracy >= 0.95;
2. mean SO(4) IID validation accuracy >= 0.95;
3. mean SO(4) primary metric exceeds baseline by at least 0.05 absolute;
4. SO(4) primary-metric standard deviation is at least 10% lower than baseline's.

Otherwise the result is not an SO(4) advance. Report the evidence without post-hoc threshold changes.

## Firewall

Before the terminal GRI-05 verdict, do not tune model widths, optimizer settings, epoch count, seeds, WORLD-0, metric definition, or thresholds. Do not add memory, curvature, learned connections, E8, language modeling, or new task families.

Execution-only changes are allowed only if tested against the pre-change equations for numerical output and gradient equivalence and recorded separately.
