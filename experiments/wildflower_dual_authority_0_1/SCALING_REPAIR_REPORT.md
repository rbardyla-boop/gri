# Dual-Authority-0.1 store scaling repair

Status: repair accepted for local differential testing; development reruns are
still pending. No GitHub activity occurred. Seed 310 remains frozen, and seeds
314/315 were not executed.

## Claim under test

For the same mutations, an incremental epistemic store can preserve the
reference store's semantic state while making ordinary local mutations visit
the affected dependency cone instead of recalculating the complete store.

## Checks

Engineering-only benchmark:

```text
PYTHONHASHSEED=0 python -m experiments.wildflower_dual_authority_0_1.engineering_benchmarks --timeout 20
```

The machine-readable result is
[`STORE_REFRESH_BENCH_0.json`](</home/thebackhand/Documents/AI/gri/experiments/wildflower_dual_authority_0_1/artifacts/STORE_REFRESH_BENCH_0.json>), SHA-256:

```text
0bf7c2c015801148b427cfafa4c540244b69f694b33c73dd95817ab9a7d6092d
```

Quality checks:

```text
PYTHONHASHSEED=0 python -m compileall -q experiments/wildflower_dual_authority_0_1  PASS
ruff check experiments/wildflower_dual_authority_0_1                       PASS
PYTHONHASHSEED=0 python -m pytest -q -W error experiments/wildflower_dual_authority_0_1/tests  36 passed
```

## Original bottleneck

`ReferenceEpistemicStore` is the preserved slow implementation. Its normal
mutation path calls `_refresh_all_statuses()`, which visits all claims and
recursively evaluates support paths. Revocation additionally builds complete
before/after effective-support maps. This is an empirical quadratic-looking
path on the synthetic fan-out graph; timing alone is not treated as a formal
complexity proof.

Reference graph-build results:

| supports | wall time | claims visited | supports visited | result |
|---:|---:|---:|---:|---|
| 100 | 0.040 s | 5,149 | 34,950 | complete |
| 500 | 0.884 s | 125,749 | 874,750 | complete |
| 1,000 | 3.984 s | 501,499 | 3,499,500 | complete |
| 2,000 | >20 s | — | — | timeout |
| 5,000 | >20 s | — | — | timeout |
| 10,000 | >20 s | — | — | timeout |

## Repair implemented

The successor store now contains both explicit implementations:

- `ReferenceEpistemicStore`: the original slow semantics, retained for
  differential comparison.
- `IncrementalEpistemicStore`: cached effective/grounded support state,
  support-to-claim and claim-to-dependent-support indexes, deterministic dirty
  worklists, and iterative cycle/descendant traversal.

Normal insertion, witness, revocation, and restoration enqueue only affected
supports/claims. A dependent support is re-evaluated only when its parent
claim's effective or grounded state changes. Full refresh remains available as
an explicit diagnostic operation and is not used by normal incremental
mutations.

The metrics graph traversal was also made iterative so a 1,000-deep optimized
graph does not depend on Python recursion depth.

## Benchmark after repair

| supports | incremental build | claims visited | supports visited | peak RSS |
|---:|---:|---:|---:|---:|
| 100 | 0.0047 s | 199 | 100 | 32,864 KiB |
| 500 | 0.0183 s | 999 | 500 | 33,580 KiB |
| 1,000 | 0.0645 s | 1,999 | 1,000 | 34,096 KiB |
| 2,000 | 0.0934 s | 3,999 | 2,000 | 36,136 KiB |
| 5,000 | 0.2451 s | 9,999 | 5,000 | 42,328 KiB |
| 10,000 | 0.4808 s | 19,999 | 10,000 | 49,368 KiB |

At graph size 1,000, one local mutation measured as follows:

| operation | reference | incremental | approximate speedup |
|---|---:|---:|---:|
| support insertion | 8.76 ms | 0.0826 ms | 106x |
| witness insertion | 24.3 ms | 0.1347 ms | 180x |
| support revocation | 16.1 ms | 0.0544 ms | 296x |
| recomputation | 70.2 ms | 0.655 ms | 107x |

The incremental local mutations visited one claim/support for isolated
insertion and revocation, and three claims/two supports for the isolated
witness case. The explicit full diagnostic refresh still scales with the whole
store by design; it is retained as a measurable diagnostic, not the mutation
algorithm.

## Semantic equivalence

All 36 tests pass. The differential tests compare normalized claims, statuses,
support packets, support kinds, parent relationships, enabled state, effective
state, grounded state, and reverse child indexes. They cover:

- every deterministic micro-case against both implementations;
- the alternate-support, recomputation, witness, diamond, and cascading paths;
- a fixed random mutation sequence with comparison after every mutation;
- revoke/restore and support insertion after revocation;
- duplicate dirty notifications and no-op witnesses;
- a 1,000-deep chain and 1,000-wide fan-out;
- cycle rejection, bounded capacity, deterministic replay, and DAG integrity.

No semantic discrepancy was found. Ledger hashes are intentionally not an
equivalence criterion because worklist event order may differ; both ledgers
replay deterministically.

## Verdict

**PASS for the engineering repair gates.** The reference and incremental stores
are semantically equivalent on the bounded hostile and random test regime, and
the benchmark shows local mutation cost tracking the affected cone on the
synthetic graphs.

This is not yet a scientific result for Dual Authority. The original seed-311
attempt remains `311-R1 = interrupted operational run, no scientific result`.

## Assumption register

- Reference semantics are preserved: **verified** by differential tests.
- Local indexes remain consistent: **verified** by normalized reverse-index
  comparisons and hostile graph tests.
- No recursion-depth dependency in the optimized path: **verified** for the
  1,000-deep chain and iterative metrics traversal.
- No NaN/Inf acceptance: **verified** by existing successor tests.
- Memory remains bounded: **verified** for the synthetic benchmark samples;
  long-running Nursery behavior remains unchecked.
- Full model scorer will complete within a practical time: **checkable but
  unchecked**; a provisional planning estimate is low single-digit minutes on
  this machine, with low confidence until 311-R2 is run.

## Credit assignment

The throughput improvement is attributable to cached support/grounding state
and dirty worklist propagation. This is isolated against the preserved
reference implementation on identical synthetic mutations. The model and
Nursery components were not changed or rerun, so no scientific credit is
assigned to the repair yet.

## Verification gap and stop/continue decision

The remaining gap is the exact development workload. After this report, the
permitted next step is to run 311-R2 with the unchanged seed, selectors,
thresholds, controls, and metrics, then 312 and 313 only if 311-R2 completes.
No qualification seed may run until those development artifacts exist and pass
their preregistered gates.

No qualification freeze is created at this stage.

## Maturity status

The store repair is defined, specified, tested, falsifiable, replayable, and
compared against a preserved variant. The overall Dual-Authority-0.1 claim is
not mature for qualification because the long-horizon development workload
remains unmeasured.
