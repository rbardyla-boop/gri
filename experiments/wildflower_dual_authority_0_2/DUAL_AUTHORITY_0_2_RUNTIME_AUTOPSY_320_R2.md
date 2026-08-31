# Dual-Authority-0.2 runtime autopsy: 320-R2

Status: engineering-only repair and profiling complete. No scientific seed was
run in this pass. `320-R2` remains `OPERATIONAL_FAILURE / TIMEOUT` with no
scientific artifact, and `320-R3` was not run.

The permanent entry in `DUAL_AUTHORITY_0_2_RUN_HISTORY.md` was not changed.

## Claim and check

Claim: the 320-R2 timeout was caused by implementation/scaling work in the
production challenge path, and the incremental dirty-cone scorer can replace
the reference implementation without changing scored semantics.

Checks used only engineering seed `424242`, arbitrary development inputs, and
the existing production-shaped episode lengths. No 320 selector or scientific
artifact was consumed.

```text
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m experiments.wildflower_dual_authority_0_2.run_dual_authority02 \
  --profile-only
```

The profile exercised 6 training episodes, 6 ordinary episodes, 3 challenge
episodes, 735 recorded transitions, all seven controls, all four scaling
sizes, serialization diagnostics, receipt generation, and profile validation.

## Bottleneck found

Before repair, `_run_challenge_episode` constructed a
`ReferenceProvenanceStore` for every challenge episode. The reference store's
`_add_support` called `_refresh_after_support_change`, which called
`_refresh_all_statuses` after each support mutation. Grounded-status checks
then recursively rebuilt support lineages through
`effective_grounded_lineage` and `lineage_fingerprint_for_parents`.

Relevant locations after repair are:

* runner store selection: `run_dual_authority02.py:873-889`;
* reference full refresh: `store.py:404`, `store.py:410`, `store.py:583`;
* recursive reference lineage work: `store.py:356-381`;
* incremental cache and dirty propagation: `store.py:661-813`.

The reduced 24-pair cProfile from before repair measured 4.116 s in
`_refresh_all_statuses`, 3.193 s in lineage fingerprinting, 2.732 s in
grounded-lineage traversal, and 145,778 calls to `canonical_hash`. The flat
100,000-event adversary was not the timeout source.

## Repairs

Only implementation/scaling code and tests changed:

1. The production challenge scorer now defaults to
   `IncrementalProvenanceStore`; `ReferenceProvenanceStore` remains an
   explicit semantic oracle.
2. Incremental claim-lineage caching was made active with dirty invalidation.
   Cache hits/misses and lineage hash work are measured.
3. Active world values, supports by stable reference, and claim keys by stable
   reference are indexed. This removes repeated full-store scans from world
   correction and evaluator lookups.
4. The control replay derives its claim capacity from the one immutable shared
   stream, so concatenated three-episode engineering replay cannot fail at the
   per-episode 8,192-claim limit. The production episode bound remains
   `design.MAX_ACTIVE_CLAIMS`.
5. Control state-mutation, historical-reconsideration, stream-length, and
   metric-scoring timings are recorded.
6. `--profile-only` and bounded `--profile-phase` modes were added. Profile
   output is not a scientific result.
7. Trace, stream, metric-transition, control-diagnostic, support-history,
   receipt, and validation costs are measured in the scientific runner.

No selector, seed, threshold, predictive parameter, metric definition,
provenance definition, control semantic, model, or Nursery file changed.

## Before and after engineering benchmark

On the same deterministic 24-pair engineering challenge:

| implementation | wall time | frames | transitions | support records |
|---|---:|---:|---:|---:|
| reference, before repair | 1.912574 s | 9 | 63 | 234 |
| incremental, before repair | 0.098532 s | 9 | 63 | 234 |
| reference, after repair | 1.883050 s | 9 | 63 | 234 |
| incremental, after repair | 0.083584 s | 9 | 63 | 234 |

The production path is therefore about 22.5x faster than the reference path
on this workload. The reference implementation remains available for
equivalence testing.

Lineage work after repair on that workload:

| implementation | fingerprint calculations | grounded traversals | bytes hashed | cache hits | cache misses | average lineage size | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 40,542 | 87,176 | 8,297,284 | 0 | 0 | 0.9981 | 1 |
| incremental | 218 | 326 | 41,484 | 556 | 326 | 0.4724 | 1 |

## Complete engineering profile

The no-allocation-tracing production-shaped profile completed in 177.00 s
wall, with 176.08 s user CPU, 0.84 s system CPU, and 779,236 kB peak RSS.
The largest phases were:

| phase | wall time |
|---|---:|
| predictive trace generation | 36.58 s |
| model training | 22.43 s |
| ordinary predictive evaluation | 19.07 s |
| DUAL_AUTHORITY replay | 31.65 s |
| DAG + witness, no recompute replay | 23.90 s |
| witness application | 7.27 s |
| provenance recomputation | 4.36 s |
| transition-stream serialization | 0.69 s |
| canonical-support accounting | 0.49 s |
| diagnostic output serialization | 0.25 s |
| Metric A/B scoring phase total | 0.41 s |
| flat scaling and affected-cone correction | below 0.02 s for corrections |
| receipt canonicalization, receipt hashing, validation | below 0.001 s each |

Allocation-traced engineering checks were also completed:

* production-shaped pipeline: 177.88 s internal wall; 180.78 s `/usr/bin/time`
  wall; 863,968 kB peak RSS; 102,388,392 B tracemalloc peak;
* three-episode challenge plus all controls plus scaling: 179.66 s internal
  wall; 182.51 s `/usr/bin/time` wall; 810,612 kB peak RSS; 137,352,028 B
  tracemalloc peak.

The full profile's output-size measurements were:

* 2,988 predictive trace rows / 3,705,676 canonical bytes;
* 735 recorded transitions / 4,994,620 canonical bytes;
* 5,145 metric-transition rows / 2,528,960 canonical bytes.

The control replay received one immutable tuple of 735 transitions; each
mechanism had independent mutable state. No seven-way stream copy was made.

## Control replay diagnostics

These are engineering-profile counts, not scientific results. Metric A has
zero opportunities in this synthetic stream and must not be interpreted as a
scientific denominator.

| control | false durable / opportunities | rollback successes / opportunities | Metric A successes / opportunities | Metric B TP / FP / FN | active supports | state mutations | historical reconsiderations | replay wall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DUAL_AUTHORITY | 0 / 9,555 | 1,745 / 1,745 | 0 / 0 | 4,729 / 0 / 0 | 19,110 | 23,520 | 4,351,277 | 31.712 s |
| DIRECT_COMMIT | 1,745 / 9,555 | 0 / 1,745 | 0 / 0 | 0 / 4,729 / 4,729 | 9,555 | 9,555 | 0 | 0.079 s |
| CONFIDENCE_COMMIT | 772 / 9,555 | 973 / 1,745 | 0 / 0 | 0 / 1,552 / 4,729 | 3,198 | 3,198 | 0 | 0.036 s |
| DAG_NO_WITNESS | 0 / 9,555 | 1,745 / 1,745 | 0 / 0 | 0 / 0 / 4,729 | 9,555 | 9,555 | 0 | 1.018 s |
| WITNESS_NO_DAG | 416 / 9,555 | 1,329 / 1,745 | 0 / 0 | 0 / 4,729 / 4,729 | 9,555 | 9,555 | 4,410 | 0.074 s |
| WITNESS_PLUS_RECOMPUTE_NO_DAG | 0 / 9,555 | 1,745 / 1,745 | 0 / 0 | 0 / 4,729 / 4,729 | 19,110 | 19,110 | 4,410 | 0.048 s |
| DAG_PLUS_WITNESS_NO_RECOMPUTE | 0 / 9,555 | 1,745 / 1,745 | 0 / 0 | 0 / 0 / 4,729 | 9,555 | 13,965 | 10,463,999 | 23.963 s |

The old full-store diagnostic scan was removed. The large reconsideration
counts above are the prescribed historical-state metric, maintained by a
counter; they are not full retained-history scans. No optimized replay path
now scans all claims merely to produce that diagnostic.

## Scaling result

The flat adversary performs one intentional O(N) correction:

| retained events | flat correction work | flat elapsed | dual correction work | dual claims visited | dual supports visited |
|---:|---:|---:|---:|---:|---:|
| 100 | 100 | ~0.000009 s | 2 | 1 | 1 |
| 1,000 | 1,000 | ~0.000186 s | 2 | 1 | 1 |
| 10,000 | 10,000 | ~0.00135 s | 2 | 1 | 1 |
| 100,000 | 100,000 | ~0.0113 s | 2 | 1 | 1 |

The 100,000 adversary is case A: intentionally O(N) once. It is not rerun
once per witness, does not rebuild history, and does not serialize a giant
intermediate state. The dual affected-cone correction is constant in this
adversary. The earlier whole-row timing included history construction; that
construction is separate from correction work.

## Semantic equivalence

The deterministic 24-pair reference/incremental comparison passed equality of:

* recorded frames and transitions;
* Metric A/B semantic summaries;
* support inventory, support identities, enabled/effective/grounded state;
* provenance fingerprints;
* graph-quality metrics;
* canonical support creation/reuse/provenance counts.

A deterministic 120-operation hostile mutation audit also matched final
claims, statuses, support inventories, effective/grounded state, and the
maintained revoked-support counter after every successful operation. Each
store's ledger replay matched its own ledger head.

One operational caveat remains: on a broader conflicting-world mutation
sequence, the incremental implementation can order status-ledger events
differently from the reference because the reference performs a full refresh
inside `observe`. The final semantic state is equal, and the exact 24-pair
comparison stream is byte-for-byte equal. This ledger-order distinction is
reported rather than treated as a scientific success claim.

## Validation and hashes

```text
python -m compileall -q experiments/wildflower_dual_authority_0_2
ruff check experiments/wildflower_dual_authority_0_2
PYTHONHASHSEED=0 python -m pytest -q -W error \
  experiments/wildflower_dual_authority_0_2/tests
```

Result: 65 tests passed; compileall and Ruff passed. The authorization tests
continue to reject seeds 314 and 315 (and all non-320 scientific execution
seeds).

Changed executable hashes:

| file | pre-autopsy hash | current hash |
|---|---|---|
| `controls.py` | `3c42de7f4cb759f0b1ad349cdff1c1db5b296f6dad85b8199c422ff61eea56e1` | `82132e1716fe42765afe8a2d23364535baf15af9b4587675ee2b37925adb7d02` |
| `run_dual_authority02.py` | `818a9b3b7bbb9fd28211dca3d34fa41eec77d7cb328d769bde5d5d027f578fab` | `02b32d9094de14894a6f68d1f918dbe6254041ed540932885359ae6423a51764` |
| `store.py` | `24620c1ac16272c2ef3a30829e4e874631b4240a00e01f63a646976422800c49` | `4cf6c0ebb09f71ac30b9be82fdc3dc6c574183135a3a359d0f457c9e80c9710e` |
| `tests/test_runner.py` | `2860fa7ffa20cc83c84f2be7f6a512734dfd56ce1133e218bcae9df97369f01c` | `33292a2c7f0c05ecdcfa68273d951d4f09b7be7d5e886d70e788dc9d6f7d9f51` |

The design, metrics, scaling, recorded-stream, model, Nursery, and guard
hashes are unchanged from the prior prelock record.

## Verdict and stop

Verdict: the R2 timeout was an implementation/scaling failure, not a
scientific failure. The repair is supported by deterministic equivalence and
engineering profiles, with the ledger-order caveat above. A conservative
projection for a future seed-320 run, including allocation tracing, controls,
scaling, output construction, and margin for workload variance, is below
10 minutes and more plausibly 4–7 minutes on this host. This is a projection,
not a scientific result.

Another exact seed-320 execution is technically justified only after this
report is reviewed and a separate authorization is given. Do not run
`320-R3` from this pass.
