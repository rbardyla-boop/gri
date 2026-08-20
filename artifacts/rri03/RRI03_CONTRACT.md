# RRI-03 — Extrapolation Stress Test

Status: **PREREGISTERED; EVALUATION ONLY; NO NEW TRAINING**

## Claim under test

The parameter-neutral immutable-anchor processor that passed RRI-02B/C remains
useful outside the original WORLD-0 evaluation regime: at recurrent depths
128–512 and on larger, branched, distractor-rich, and corrupted graphs, it
will retain a measurable advantage over the matched recurrent baseline.

RRI-03 evaluates the already-trained RRI-02B checkpoints. This preserves the
paired initialization, 30,912-parameter identity, optimizer budget, and five
training seeds while isolating out-of-distribution evaluation. No model is
retrained and no WORLD-0 file is changed.

## Frozen models

- Baseline: hidden `49`, message `51`, 30,912 trainable parameters.
- Anchor: hidden `49`, message `51`, 30,912 trainable parameters.
- Anchor law: `a=h0`, `h_anchor=(h+a)/2`.
- Training provenance: the frozen RRI-02B 80-epoch, depth-4, AdamW runs.
- Evidence seeds: `1337–1341`.

## Deterministic stress matrix

Every scenario contains eight cases, one for each WORLD-0 directional relation.
The cases are generated after the architecture was frozen using deterministic
scenario seeds. The oracle is the known target-path relation; distractor
components do not touch the query path except where branching is explicitly
specified.

| Family | Scenarios | Recurrent steps |
|---|---|---:|
| Depth | chain lengths 128, 256, 512 | 128, 256, 512 |
| Scale | 128, 256, 512, 1024 entities with a 4-edge target chain and disconnected distractors | 16 |
| Structure | branching paths, disconnected distractor paths, simultaneous relation chains, new long compositions | 32 |
| Corruption | irrelevant edges, missing irrelevant facts, contradictory disconnected distractor cycle | 32 |

The scale/structure/corruption cases use 128 entities unless their scenario
definition specifies a larger scale. Contradictory distractors are outside the
query component; the local query oracle remains the target path relation.

The implementation precomputes the unchanged adjacent-pair index once per
case. A structural preflight compares this execution-only optimization with
the original recurrent equations at steps 1 and 4 before stress evaluation.

## Primary metric

For each model and seed, compute the mean accuracy of each scenario. First
average within the four families, giving each family equal weight; then:

```text
P_stress = mean(depth_family, scale_family, structure_family, corruption_family)
```

This prevents the four scale cases from dominating the three other questions.
All scenario and family scores remain reported separately.

## Frozen interpretation gates

RRI-03 records a stress advantage only if all gates pass:

1. `mean(P_stress_anchor - P_stress_baseline) >= .05`.
2. Anchor depth-family improvement is at least `.05`.
3. Anchor wins paired `P_stress` on at least `4/5` seeds; ties do not win.
4. Anchor is not more than `.05` below baseline in any non-depth family.

These are evaluation gates, not a new training claim. Seed 1341 remains in all
aggregates and receives a dedicated paired comparison.

## Stop rule

RRI-03 stops after the deterministic stress verdict. No memory, dimensional
memory consolidation, adaptive halting, learned connections, geometry, E8, or
language experiment is authorized by this unit.
