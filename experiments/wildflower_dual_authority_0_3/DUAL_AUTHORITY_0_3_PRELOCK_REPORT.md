# Dual-Authority-0.3 prelock report

Status: local engineering prelock. No scientific seed 340, 341, 342, 350, or
351 has been executed.

## Claim under test

An explicit alternate-evidence workload with canonical grounded root lineage
will make Metric A non-vacuous and falsifiable, while preserving the frozen
predictive authority path, transitive provenance semantics, safety gates,
dirty-cone implementation, and seven-control comparison.

## Checks performed

- Created a separate `wildflower_dual_authority_0_3` package by carrying
  forward the 0.2 architecture.
- Kept the 0.2 package and seed-320-R3 artifact unchanged.
- Added 40 deterministic valid alternate-evidence events per episode and the
  18-behavior hostile contract. Case 1 is intentionally represented by the
  guaranteed-positive events; codes 2--18 are emitted as additional hostile
  events.
- Defined root-lineage independence from complete numeric world packets and
  transitive grounded root sets.
- Added evaluator-side event records with pre/post path counts, invalidated
  and surviving path IDs, classifications, and separate A/B booleans.
- Kept truth and event labels out of `MechanismFrame`.
- Kept Metric B targets on the carried-forward Nursery transition path; the
  alternate challenge does not double-credit Metric B.
- Kept all seven controls real and independent, including the flat
  witness-plus-recompute control with no provenance capability.
- Kept `IncrementalProvenanceStore` as the production scorer and
  `ReferenceProvenanceStore` as semantic oracle/test implementation.
- Added fail-closed authorization for development seeds 340–342 and locked
  qualification seeds 350–351. Prior 0.1/0.2 seeds are rejected.
- Ported `run_dual_authority03.py` and verified CLI help.
- Added deterministic hostile-case and Reference/Incremental equivalence
  tests.

## Local evidence

The direct challenge harness produced the following deterministic result for
one episode with 40 guaranteed-positive events plus 17 additional hostile
events. This resolves the former 57/58 ambiguity: case 1 is covered by the
guaranteed-positive construction and is not emitted a second time.

```text
events                              57
guaranteed positive events          40
emitted hostile codes               2--18 (17 additional events)
represented hostile behaviors       1--18 (all 18)
expected positive hostile codes     1, 8, 9, 10, 12
expected Metric-A opportunities     44
actual Metric-A opportunities       44
actual Metric-A successes           44
Metric-A rate                       1.0
false opportunity classifications   0
Metric-B diagnostic events          2 / 2
```

Across the three profile episodes the same classifier produced 171 events,
120 guaranteed positive events, and 132 expected/actual opportunities with
132 successes. The profile is engineering evidence only; it is not a
scientific model-seed result.

## Engineering profile

Command:

```text
/usr/bin/time -v env PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m experiments.wildflower_dual_authority_0_3.run_dual_authority03 \
--profile-only --output /tmp/wildflower03_profile.json
```

Observed:

```text
exit status                    0
wall time                      4:33.01
user CPU                       271.71 s
system CPU                     1.18 s
maximum RSS                    799032 kB
scientific selectors used     false
alternate events               171
guaranteed opportunities       120
Metric-A opportunities         132
Metric-A successes              132
Metric-B diagnostics           2 / 2
all seven control states       present
```

The run is below the 30-minute watchdog and below the 10-minute engineering
target. The profile exercised the predictor pipeline, challenge construction,
control replay, serialization, and scaling sections without executing a
scientific seed.

## Required validation

The prelock validation commands are:

```text
python -m compileall -q experiments/wildflower_dual_authority_0_3
ruff check experiments/wildflower_dual_authority_0_3
PYTHONHASHSEED=0 python -m pytest -q -W error experiments/wildflower_dual_authority_0_3/tests
python -m experiments.wildflower_dual_authority_0_3.run_dual_authority03 --help
```

They pass locally. The test suite covers canonical identity, all 18 hostile
cases, exact denominator construction, sidecar quarantine, deterministic
Reference/Incremental equivalence, seed guards, selectors, controls, and
runner interfaces.

## Scientific gates and stop

Seed 340 is technically ready only after source-hash and frozen-material
checks are recorded below. If it is later run, its artifact must validate
JSON, seed, selectors, all seven controls, finite values, Metric-A and
Metric-B opportunity counts, zero false opportunity classifications,
deterministic ledger replay, active-store bound, source hashes, and semantic
receipt. A nonzero false-opportunity count yields an epistemic scientific
`FAIL` gate in the completed artifact; it is not converted into an operational
runner crash. Then report predictive authority,
epistemic preservation, epistemic recomputation, safety, control comparison,
scaling, and deterministic replay independently.

No conclusion may be drawn from the engineering profile as to predictive
authority, scientific epistemic success, or architecture qualification.

## Assumptions and credit assignment

The Reference store is the semantic oracle. The Incremental store is the
implementation under test. The evaluator may inspect truth and frozen store
snapshots after mechanism mutation, but those values are excluded from the
mechanism input. Controls consume identical frames and do not share state.

Positive Metric-A credit is assigned only to a pre-existing independent
survivor. A post-witness path is diagnostic recomputation, never preservation.

## Verification gap

No fresh scientific model seed has been completed. Predictive gates, scientific
control superiority, and generalization remain open. The alternate challenge
has engineering evidence but no scientific result. The profile measures
engineering behavior, not a qualification workload.

## Stop / continue

**STOP.** Do not execute seed 340 until this report, the preregistration, the
alternate-evidence contract, source hashes, and frozen-material checks have
been reviewed. Do not execute 341, 342, 350, or 351. Do not tune any
parameter. Do not perform GitHub activity.

## Maturity

Prelock engineering evidence only. The 0.3 successor is not scientifically
qualified and is not an architecture-success claim.

## Frozen checkpoint and hashes

Historical checkpoint: `77d25c6a60ad1556d20ab5fbd82897f7b0e50fee`.

Seed-320-R3 artifact SHA-256:
`db51486f9e72b11bb2f4f6ec97642f4e0c6c15c61bc88f48fff345d81d13fe9b`.

The final 0.3 source hash manifest is recorded after the final validation
pass. Documentation is not executable scientific input.

```text
08e0c8a58b5c4fc272ea30f3d8bb62da540bc9a3600193907f803c0297ed5d34  successor/__init__.py
6af28e9217889654ab9182771ec7896fd462655ad1f9a168a7cc18ae4f33d020  successor/alternate_evidence.py
82132e1716fe42765afe8a2d23364535baf15af9b4587675ee2b37925adb7d02  successor/controls.py
437efaa689f674398d319a9c3ab6048a692f1af210a87f2905c6bf28793d8013  successor/design.py
599cb592abc5974e3f314a52e873c4ca89b61142d3a0cc435cf5eccfde076ab9  successor/metrics.py
f0454c4ba5b056fd6c32437ae9c45fb79470958db8e9808dd5e54951413ba658  successor/micro_simulations.py
cc9c71174035c0c438a7b55da1d769ec74c2d3cc44a7fa036912605151bec68e  successor/predictive_trace.py
3ede09df598f29c030f048d680b6435b64bc6039c6416609b148535611e93d64  successor/qualification_guard.py
3746c58accd12d86aa5693d6e985a01e106cc58db83f562514231c773e49606e  successor/recorded_stream.py
c2bec3233280c82c07950face49f647b524bc52c9d37b0eefa5babd689004c3a  successor/run_dual_authority03.py
b2eb4d64c8dbc668ce9dd265b3178fd9d4071210255e27964cd587df88717de1  successor/scaling.py
4cf6c0ebb09f71ac30b9be82fdc3dc6c574183135a3a359d0f457c9e80c9710e  successor/store.py
e0ae09ce898be89c069bd83504205ea51c9ec7658d15b0c383fc16b31166982e  successor/tests/test_alternate_evidence.py
8edd3ee9f43c359b2b3475dbea85a3ec36e3f62724ad19e3f49faf8d80880706  successor/tests/test_controls.py
e6aff30ba128bef2be56a85443b01b5048a57906d53a91b0b50090bcade9468b  successor/tests/test_prelock_interfaces.py
ecf4d3f34a2239c8fc8a3118e04638e6cb6f0b10b8199f0f6bc840ce4a37e8c4  successor/tests/test_provenance_contract.py
4a61b678522fbeaee0185350c25c362ba82a1563da14a5c5914bf7ab3c47ff84  successor/tests/test_runner.py
97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1  historical/probe_innovation_model.py
13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e  historical/qualify_authority190.py
a402e99c6374fffa23af4a2ef1e32a67141c41cf7ece020c12fe2974e65753d6  historical/wildflower0/nursery1.py
```
