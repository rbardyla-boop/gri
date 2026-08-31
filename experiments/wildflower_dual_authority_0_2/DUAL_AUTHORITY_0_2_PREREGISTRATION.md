# Dual-Authority-0.2 preregistration

Status: local prelock draft. No 0.2 development or qualification seed has
been executed. Seed 311 discovered the repair and therefore cannot validate
it.

## Scope and frozen carry-forward

Dual-Authority-0.1 remains the historical FAIL under its original gates:

- Metric A: 1784/1784;
- frozen Metric B: 2306/2708;
- post-result semantic recovery audit: 2708/2708;
- all 402 apparent failures were REL_ORDER_PARITY transitive-lineage cases;
- exact prediction-to-recompute duplicates: 2223;
- predictive H8 failure remains genuine and unresolved;
- control superiority was not established.

The 0.2 first development pass leaves the predictive mechanism, model
parameters, thresholds, controls, Nursery world, selectors’ semantic purpose,
and epistemic meaning unchanged. It changes only provenance representation,
incremental propagation instrumentation, and the independence of controls.

Natural language is outside the cognitive path.

## Preregistered seeds and selectors

Development seeds are `320, 321, 322`. Qualification seeds are `330, 331`.
The reserved 0.1 range `311–315` is forbidden. Selector starts are generated
by `design.selector_starts` from base `2,000,000`, with a 200,000 slot width;
training, ordinary test, and challenge ranges begin at slot offsets 0, 50,000,
and 100,000 respectively, each with width 50,000. These ranges are disjoint
from the 0.1 800,000-based range.

Qualification is fail-closed until a local authorization file exists. The
authorization file is intentionally absent in this prelock state.

## Scientific runner authorization

The 0.2 runner is implemented and validated locally, but no scientific seed
has been executed in this prelock pass. The only separately authorized
development command, when explicitly approved, is:

```text
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m experiments.wildflower_dual_authority_0_2.run_dual_authority02 --seed 320
```

The runner must reject seeds 321, 322, 330, 331, and all reserved 0.1 seeds.
The runner writes a validated result atomically and records source hashes,
runtime/resource measurements, and a deterministic semantic receipt.

## Predictive authority

For each ordinary episode report H1, H8, H32, event-only H8, and ungated
learned-vs-null ratios. Gates remain:

```text
h1 maximum ratio       <= 1.10
h8 maximum ratio       <= 1.00
h8 mean ratio          <= 0.90
h32 maximum ratio      <= 1.00
h32 mean ratio         <= 0.85
event-H8 mean ratio     <= 0.90
```

The 0.2 trace schema records innovation score, authority, null error,
ungated-learned error, gated error, exact H8 predictions, mode, episode seed,
step, and evaluator-side event locations. Episode `1931950002`, mode 1, H8
ratio `1.038178`, authority mean `0.907365` is not a tuning target.

## Epistemic authority

Metric A uses the exact opportunity and success definition in the provenance
contract. It requires at least 30 opportunities and rate 1.0.

Metric B uses exact global TP/FP precision and TP/opportunity recall, with at
least 30 opportunities. Both precision and recall must be 1.0. Episode-level
values are displayed separately and never averaged to form the global gate.

Safety gates are:

```text
false durable claim rate        = 0
rollback recall                 = 1
stale support survival rate     = 0
duplicate support rate          = 0
orphan support rate             = 0
support DAG integrity            = true
active store bound               = true
deterministic replay             = true
```

## Independent controls

All seven mechanisms consume the same recorded transition stream and maintain
independent state:

1. `DUAL_AUTHORITY`: witnesses, semantic dependency DAG, grounded provenance,
   and recomputation;
2. `DIRECT_COMMIT`: immediate prediction commitment only;
3. `CONFIDENCE_COMMIT`: immediate commitment above the preregistered 0.50
   confidence threshold;
4. `DAG_NO_WITNESS`: dependency DAG without world witnesses;
5. `WITNESS_NO_DAG`: flat witness retraction without dependency tracking;
6. `WITNESS_PLUS_RECOMPUTE_NO_DAG`: flat witness plus full recomputation,
   explicitly without provenance query capability;
7. `DAG_PLUS_WITNESS_NO_RECOMPUTE`: DAG and witness retraction without
   recomputation.

The no-DAG recompute control is a real flat mechanism, not an evaluator-side
summary and not a store with provenance metadata hidden behind a flag.

Report false durable claims, durable coverage, stale descendants, rollback,
Metric A, Metric B, recomputation precision/recall, provenance capability,
supports touched per correction, historical state reconsidered per witness,
active support count, runtime, and memory growth side-by-side.

## Scaling adversary

The no-DAG recompute control is benchmarked on 100, 1,000, 10,000, and
100,000 retained history events where practical. Each correction scans every
retained event and reports correction work, elapsed time, and retained memory
proxy. Dual Authority may claim a scaling advantage only if the measured
control work establishes one; no superiority is assumed in advance.

## Stop rules

Do not run a seed until this prelock document, the provenance contract, source
hashes, hostile tests, independent controls, and validation commands have been
reviewed. Do not tune against spent seeds. After the first authorized 0.2
development seed, stop and review before any further seed.
