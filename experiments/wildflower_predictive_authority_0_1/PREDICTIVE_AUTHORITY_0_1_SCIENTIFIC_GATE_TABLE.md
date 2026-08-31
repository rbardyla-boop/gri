# Predictive Authority 0.1 — Scientific Gate Table

All gates below are frozen before seed 360. The unit of ordinary predictive
scoring is an eligible rollout origin. Episode ratios are computed from sums
over origins within each episode. Equality passes. A missing population or
zero denominator fails closed; it is not silently treated as a pass.

| name | population | formula | threshold | PASS rule | zero-denominator rule |
|---|---|---|---:|---|---|
| old H1 max | each ordinary episode | `max_episode(sum(gated H1 error) / sum(NULL H1 error))` | `1.10` | value `<= 1.10` | fail |
| old H8 max | each ordinary episode | `max_episode(sum(gated H8 error) / sum(NULL H8 error))` | `1.00` | value `<= 1.00` | fail |
| old H8 mean | ordinary episodes | `mean_episode(sum(gated H8 error) / sum(NULL H8 error))` | `0.90` | value `<= 0.90` | fail |
| old H32 max | each ordinary episode | `max_episode(sum(gated H32 error) / sum(NULL H32 error))` | `1.00` | value `<= 1.00` | fail |
| old H32 mean | ordinary episodes | `mean_episode(sum(gated H32 error) / sum(NULL H32 error))` | `0.85` | value `<= 0.85` | fail |
| old event-H8 mean | episodes with at least one event-bearing origin | `mean_episode(sum(gated H8 error) / sum(NULL H8 error))` over origins whose event lies in the next 8 steps | `0.90` | value `<= 0.90` | fail |
| H8 worse-learned protection | origins where `learned H8 error > NULL H8 error` | `sum(gated H8 error) / sum(NULL H8 error)` | `1.05` | value `<= 1.05` and at least 30 origins | fail; fewer than 30 also fails |
| H8 useful-learner capture | origins where `learned H8 error < NULL H8 error` | `sum(NULL H8 error - gated H8 error) / sum(NULL H8 error - learned H8 error)` | `0.50` | value `>= 0.50` and at least 30 origins | fail; fewer than 30 also fails |
| H1 global regression | all ordinary origins | `sum(gated H1 error) / sum(NULL H1 error)` | `1.05` | value `<= 1.05` | fail |
| H32 global non-inferiority | all ordinary origins | `sum(gated H32 error) / sum(NULL H32 error)` | `1.05` | value `<= 1.05` | fail |
| H8 nontrivial fraction | all ordinary origins, one mean authority per origin | `count(mean_origin_H8_authority > 0.10) / count(origins)` | `0.05` | value `>= 0.05` | fail |
| H8 nontrivial mean | all ordinary origins | `mean(mean_origin_H8_authority)` | `0.05` | value `>= 0.05` | fail |

## Machine-readable comparator contract

The table above is the frozen scientific definition. The executable evaluator
uses the following exact key/operator/threshold contract in
`design.GATE_CONTRACT`, and every numeric gate comparator routes through
`design.gate_passes`. This is an implementation invariant, not a new gate or
a threshold change.

| contract key | operator | threshold |
|---|---:|---:|
| `old_h1_max` | `<=` | `1.10` |
| `old_h8_max` | `<=` | `1.00` |
| `old_h8_mean` | `<=` | `0.90` |
| `old_h32_max` | `<=` | `1.00` |
| `old_h32_mean` | `<=` | `0.85` |
| `old_event_h8_mean` | `<=` | `0.90` |
| `h8_worse_learned_protection` | `<=` | `1.05` |
| `h8_useful_learner_capture` | `>=` | `0.50` |
| `h1_global_regression` | `<=` | `1.05` |
| `h32_global_noninferiority` | `<=` | `1.05` |
| `h8_nontrivial_fraction` | `>=` | `0.05` |
| `h8_nontrivial_mean` | `>=` | `0.05` |

Equality passes for every comparator. Population eligibility and denominator
checks remain separate fail-closed conditions in the evaluator. In
particular, negative captured gain remains in the H8 useful-learner numerator;
it is not clipped before applying the `>= 0.50` gate.

## Exact subset definitions

Useful and worse-than-null membership is per origin and H8-specific. The
definitions are strict:

```text
H8 useful: learned_H8_error < NULL_H8_error
H8 worse:  learned_H8_error > NULL_H8_error
```

Equal errors belong to neither subset. Errors are non-negative. Because a
useful origin has `NULL_H8_error > learned_H8_error >= 0`, its available-gain
denominator is positive; nevertheless a zero aggregate denominator fails
closed. Negative captured gain is retained in the numerator and is not clipped
to zero.

For nontriviality, each eligible origin's H8 authority is the arithmetic mean
of its eight recorded per-step authority values. The reported population mean
is then the arithmetic mean of those per-origin means across *all* eligible
origins, including origins with zero authority.

## Evaluator/mechanism boundary

Subset membership, target errors, and the four-way model/policy classification
are evaluator-only. They never enter `AuthorityContext` or any candidate
policy. The primary candidate is the only policy that receives the scientific
PASS/FAIL verdict; P0–P6 and disagreement gating are comparators/diagnostics.
