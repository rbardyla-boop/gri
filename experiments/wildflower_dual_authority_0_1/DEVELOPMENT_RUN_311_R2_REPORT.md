# Dual-Authority-0.1 — development run 311-R2

## Claim under test

With the repaired incremental store, the preregistered Dual-Authority-0.1
scorer can complete seed 311 without changing the scientific design and can
measure predictive authority, alternate-support preservation,
recomputation, safety, controls, and deterministic replay.

## Execution record

- Checkout: `/home/thebackhand/Documents/AI/gri`
- Branch: `wildflower-local-lab`
- HEAD: `77d25c6a60ad1556d20ab5fbd82897f7b0e50fee`
- Start: `2026-08-29T14:17:22-03:00`
- Command:

  ```text
  timeout --signal=TERM --kill-after=10 1800s /usr/bin/time -v env PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m experiments.wildflower_dual_authority_0_1.run_dual_authority01 --seed 311
  ```

- Python: 3.12.3
- NumPy: 2.2.6
- Torch: 2.8.0+cu128
- Qualification guard: explicitly blocks 314 and 315
- GitHub activity: none

The first completed execution produced the same scientific aggregate but
failed artifact validation because the scorer omitted the `DUAL_AUTHORITY`
control row. That reporting-only defect was corrected without changing seed,
selectors, thresholds, metrics, controls' behavior, Nursery data, predictive
parameters, or epistemic semantics. The run documented here is the corrected
311-R2 artifact.

Primary artifact:
[`development_seed311.json`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/artifacts/development_seed311.json>)

Artifact SHA-256:

```text
b51de9e7e7221c23226f95507fea446444645fc9279d5e99398049c81e78c58
```

The artifact's semantic receipt is present and independently recomputes to:

```text
971852b2ae87a5a2985a3d4c499ac9b05f3b1ea6941dc856ab070929dd136582
```

## Artifact validation

PASS:

- valid JSON;
- `model_seed == 311`;
- exact preregistered selectors;
- all seven control names;
- required aggregate metrics and opportunity counts;
- finite numeric values with no NaN/Inf;
- source hashes match the local source files;
- semantic receipt matches the canonical hash;
- deterministic replay true;
- active-store bound intact.

## Predictive authority

| metric | mean | maximum | gate |
|---|---:|---:|---|
| h1 ratio | 0.970356 | 1.041738 | PASS |
| h8 ratio | 0.924816 | 1.038178 | FAIL |
| h32 ratio | 0.810279 | 0.999437 | PASS |
| event h8 ratio | 0.924748 | 1.038178 | FAIL |
| ungated h1 maximum | — | 1.297877 | diagnostic |

The predictive gate aggregate is **FAIL**: h1 non-inferiority and both h32
criteria pass, but h8-all, h8-mean, and event-h8-mean criteria fail.

## Epistemic authority

Metric A — genuine alternate-support preservation:

```text
opportunities: 1784
successes:    1784
rate:         1.000000
```

Metric A is a substantial-N **PASS**.

Metric B — recomputation after parent change:

```text
opportunities: 2708
successes:    2306
rate:         0.851551
precision:    0.511589
recall:       0.849114  (mean per episode)
```

Metric B is a **FAIL** against the preregistered precision/recall-1.0 gates.
The aggregate success/opportunity rate and mean episode recall differ because
the artifact reports both aggregate and per-episode forms.

## Safety and graph quality

```text
rollback:                 2171 / 2171 = 1.000000
false durable claims:     0 / 9555 = 0.000000
stale support survival:   0.000000
duplicate support rate:   0.116327
orphan support rate:      0.000000
DAG integrity:             true
durable coverage:         8895 / 9555 = 0.930926
cycle attempts rejected:  0
deterministic replay:     true
```

Safety is a **PASS**. Duplicate support rate is nonzero and remains a hostile
interpretation concern, even though no orphan or stale support survived.

## Scaling

From `/usr/bin/time -v`:

```text
wall time:       1:15.20
CPU time:        75.09 s (74.41 user + 0.68 system)
peak RSS:        766896 KiB
```

The scorer's incremental scaling probe reported:

| episode length | wall time | peak Python bytes | active claims | supports |
|---:|---:|---:|---:|---:|
| 32 | 0.304 s | 0.97 MiB | 439 | 832 |
| 64 | 0.617 s | 2.04 MiB | 881 | 1,664 |
| 128 | 1.331 s | 4.15 MiB | 1,762 | 3,328 |
| 256 | 2.501 s | 8.31 MiB | 3,530 | 6,656 |

All scaling-probe ledgers replayed deterministically. The active claim bound
was not exceeded. Dirty-claim/support counters were not serialized by the
scored runner; they are available in the engineering benchmark, but are not
silently substituted for run-311 measurements.

Operational scaling is **PASS** for this completed workload, with the stated
instrumentation gap.

## Controls

The scorer records exact false-durable counts and coverage for all seven
control summaries. It records preservation/recomputation counts only for the
Dual-Authority row, and it does not run seven independent stores. Therefore
`not collected` below is an evidence limitation, not a zero.

| control | false durable | false rate | durable coverage | stale descendants | Metric A | Metric B |
|---|---:|---:|---:|---:|---|---|
| DUAL_AUTHORITY | 0 | 0.000000 | 0.930926 | 0 | 1784/1784 | 2306/2708 |
| DIRECT_COMMIT | 2171 | 0.227211 | 0.772789 | not collected | not collected | not collected |
| CONFIDENCE_COMMIT | 1577 | 0.165044 | 0.478493 | not collected | not collected | not collected |
| DAG_NO_WITNESS | 0 | 0.000000 | 0.000000 | not collected | not collected | not collected |
| WITNESS_NO_DAG | 616 | 0.064469 | 0.000000 | 616 | not collected | not collected |
| WITNESS_PLUS_RECOMPUTE_NO_DAG | 0 | 0.000000 | 1.000000 | not collected | not collected | not collected |
| DAG_PLUS_WITNESS_NO_RECOMPUTE | 0 | 0.000000 | 0.489377 | not collected | not collected | not collected |

For the Dual-Authority row, rollback was `2171/2171`; separate rollback counts
for the other six control summaries were not collected. Control superiority is
therefore **INSUFFICIENT**, despite strong directional evidence against direct
commit, confidence-only, witness-without-DAG, and DAG-without-witness.

## Hostile interpretation

1. **Witness alone explains everything:** not supported. `WITNESS_NO_DAG`
   leaves 616 stale descendants and 616 false durable claims.
2. **Recompute-everything explains everything:** it explains the zero false
   durable summary and full coverage in its control, but has no provenance and
   does not establish Dual Authority's preservation mechanism.
3. **DAG alone explains everything:** not supported. `DAG_NO_WITNESS` has zero
   durable coverage.
4. **Metric A denominator is tiny:** not supported; N=1,784.
5. **Metric B denominator is tiny:** not supported; N=2,708.
6. **Duplicate support inflates success:** unresolved concern; duplicate rate
   is 11.63%, and the scorer does not provide a duplicate-excluded A/B audit.
7. **Aggressive revocation makes safety look good:** partly unresolved. Safety
   is perfect, but coverage is 93.09% and recomputation recall/precision fail;
   no separate temporary-knowledge-loss metric was recorded.
8. **Regeneration latency hides loss:** Metric A is evaluated after witness
   and before recomputation, so its preservation result is not explained by
   regeneration. No per-transition latency trace was recorded.
9. **Bounded storage favors one mechanism:** unlikely in this run; challenge
   maximum claims was 19 versus an 8,192 bound, and the scaling probe peaked at
   3,530 claims.
10. **Instrumentation changes state/timing:** snapshots are read-only and
    semantic replay is deterministic, but there was no instrumentation-ablation
    run and control summaries are evaluator-side approximations.

## Final classification

```text
predictive mechanism:       FAIL
epistemic preservation:     PASS (N=1784)
epistemic recomputation:    FAIL (N=2708)
safety:                     PASS
control superiority:        INSUFFICIENT
scaling:                    PASS for completed workload
deterministic replay:       PASS
```

Overall 311-R2 is a **scientific FAIL**, localized to predictive h8 criteria
and recomputation precision/recall. It is not evidence that the entire
Dual-Authority concept fails. No changes were made in response to the result,
no qualification freeze was created, and execution stops here. Seed 312 is not
started.

