# Dual-Authority-0.1 local pre-lock report

Status: **STOPPED BEFORE QUALIFICATION**

No GitHub activity occurred. No model-training or scored execution was run for
seeds 310, 311, 312, 313, 314, or 315. The only executions were deterministic
local micro-simulations and tests.

## Historical evidence preserved

The seed-310 artifact remains at
`../wildflower0_prelock/artifacts/dual_authority0_run1.json` with SHA-256
`7288b38af1e5437084a255a864229580ea821988287999951db7e29cca0eb02a`.

Its frozen verdict remains `EPISTEMIC_AUTHORITY_FAILED`. No seed-310 source,
authorization, preregistration, result, or receipt was edited.

## Autopsy finding

The original preservation denominator included correct derived values whose
original parent claim keys had been invalidated. Those cases are correct
recomputation-after-parent-change cases, not alternate-support preservation
cases. The graph correctly preserves a child when its parent claim keys remain
world-valid and correctly rebuilds a child from corrected parent keys.

The successor separates these cases in `metrics.py` and documents the frozen
definitions in `DUAL_AUTHORITY_0_1_PREREGISTRATION.md`.

## Development evidence

All 16 required adversarial micro-simulations pass and capture deterministic
store snapshots before and after each public transition:

1. one bad support plus one valid alternate;
2. two bad supports;
3. two supports sharing one invalid parent;
4. alternate support with independent parents;
5. correct derived value with both parents corrected;
6. correct value reconstructed from new parent keys;
7. derived value changes after corrected parents;
8. three-level cascading descendants;
9. diamond-shaped support graph;
10. cycle attempt rejected without mutation;
11. duplicate support insertion;
12. support-removal order independence;
13. witness before recomputation;
14. multiple witnesses correcting one parent;
15. contradictory witnesses with a descendant;
16. bounded store rejects provenance eviction without mutation.

The micro-harness also checks finite state inputs, integer packet fields,
duplicate IDs, reverse child-index integrity, cycle freedom, replay hashes,
order independence, and fail-closed active-claim bounds.

## Quality results

- `python -m compileall -q experiments/wildflower_dual_authority_0_1`: PASS
- `ruff check experiments/wildflower_dual_authority_0_1`: PASS
- `pytest -W error experiments/wildflower_dual_authority_0_1/tests`: **30 PASS**
- mypy: not installed; no type-check run was claimed

The two unused-import findings in the historical seed-310 files remain
untouched as required.

## Graph-bug determination

No actual graph bookkeeping bug was found in the exercised cases. The support
graph preserves genuine alternate parent support, recursively invalidates
unsupported descendants, rejects cycles, retains provenance records, and
replays its numeric ledger deterministically.

The remaining distinction is semantic:

- if preservation means continuity through surviving parent claim keys, the
  corrected Metric A is cleanly testable;
- if preservation means retaining a correct conclusion after parent values
  change, that is actually recomputation and must be measured as Metric B.

Witness-before-recomputation order is intentional and preregistered. Changing
that order would conflate the two metrics again.

## Controls and proposed gates

The successor retains `DIRECT_COMMIT`, `CONFIDENCE_COMMIT`, `DAG_NO_WITNESS`,
and `WITNESS_NO_DAG`, and adds
`WITNESS_PLUS_RECOMPUTE_NO_DAG` and `DAG_PLUS_WITNESS_NO_RECOMPUTE`.

Proposed qualification gates are at least 30 opportunities for each metric;
Metric-A preservation rate `1.0`; Metric-B precision and recall `1.0`; stale
support survival `0.0`; false durable claim rate `0.0`; rollback recall `1.0`;
duplicate/orphan rates `0.0`; DAG integrity, active bound, and deterministic
replay all true; and control contrasts showing identifiable contributions from
witnessing, dependency tracking, and recomputation.

## Seeds and lock status

- development/mechanism shakeout: `311`, `312`, `313` — reserved, not run;
- untouched qualification: `314`, `315` — reserved and locked;
- seed `310` — spent historical evidence, excluded;
- successor selector ranges — disjoint blocks beginning at 800,000.

`qualification_guard.py` rejects seeds 314 and 315 because no local
`QUALIFICATION_AUTHORIZATION.json` exists. This report is the required stop
point before any qualification authorization is considered.

## Successor source hashes

```text
DUAL_AUTHORITY_0_1_PREREGISTRATION.md  6196e50d29bccf8a7a25b73f1f483fb1845b176908c83b4f3f493fabb16258df
README.md                               e870108d3e8c9e0fcbacf31e55ac722c11087f32a3cd0d26e5d960ad06d68d3f
__init__.py                             583c82bcb2d97769ab770ef86e70f39b53af7b90b8bc0e6f6e06c3c0cfcbfaf7
controls.py                             4d0d415017ce2a4296601e0c474288dbfac292adbba07259b3bb7e170bd312a8
design.py                               c22400920d69c6e9dfadb006895eb5f26144018d1a1bb3ac5bc0dba8ea4c923d
metrics.py                              6f09f361266dc1916f7ae3d3fbed8ff32856822d5ff433bb87ee39b03c690ab7
micro_simulations.py                    2616018a74660a3ccd481a53a6ee9f27ddeb221fed6a806bf9a3e28074b7d0d4
qualification_guard.py                  85481451b8879c126c2bade6adfe973f0f684e14c01f835fd373b2ac75d8008e
store.py                                70b9639fc562a5f2e47e312c848b2ae0bceb2c0e3542355df5f08ac28ea33bcd
tests/test_micro_simulations.py         99cc64d0133a5cbf9885df5ed61d0eff8f143c6dafd99e1d04780c68441239b2
```
