# Dual-Authority-0.2 prelock report

Status: PRELOCK REFRESH AFTER 320-R1 OPERATIONAL REPAIR; no scientific seed run.

## Claim under test

Separating semantic parent claim keys from exact grounded support-lineage
identity should repair the seed-311 transitive provenance defect while
preserving safety, deterministic replay, bounded storage, and local dirty-cone
propagation. An independently implemented flat recompute control must remain a
genuine competitor.

## Checks performed

- Created a separate `wildflower_dual_authority_0_2` package; 0.1 files and
  frozen seed-311 history were not edited.
- Added a canonical SHA-256 lineage fingerprint to derived supports.
- Added lineage validity checks, canonical support reuse, event history, and
  ledger replay.
- Added reference and incremental stores and checked semantic equivalence in
  deterministic hostile mutations.
- Added all 15 requested transitive/duplicate/replay/rollback/affected-cone
  test classes.
- Added seven independent control implementations over a quarantined recorded
  stream. No-DAG recompute has no provenance query capability.
- Added the 100/1,000/10,000/100,000 recompute-everything benchmark interface.
- Added evaluator-side predictive trace schema without changing predictive
  parameters.
- Added a fail-closed 0.2 qualification guard.
- Added the fail-closed scientific runner with atomic JSON output, source
  integrity checks, deterministic semantic receipts, resource measurements,
  all seven controls, and the four preregistered scaling sizes.
- Added 18 runner/interface tests covering authorization, selector exactness,
  truth quarantine, controls, provenance identity, scaling, serialization,
  atomic output, source integrity, and CLI help.
- Recorded `320-R1` as an operational failure only; no scientific artifact or
  scientific verdict exists for that run.
- Repaired the single stable-reference versus `ClaimKey` lookup mismatch and
  added deterministic regression coverage for the exact `KeyError`.

## Current verdict

The implementation contract is testable and the prelock checks are
inconclusive about scientific success. No fresh seed has been executed, so
there is no 0.2 PASS/FAIL result and no claim of architecture qualification.
The scientific runner is ready for a separately authorized seed-320 run but
was not invoked after the R1 repair. Seed 320 has still produced no
scientific evidence.

## Verification criteria

The first authorized development run must validate JSON, seed, selectors,
controls, finite metrics, opportunity counts, deterministic ledger replay,
active-store bound, source hashes, and semantic receipt. It must then report
predictive authority, Metric A, Metric B global and episode-level values,
safety, scaling, and all seven controls. The preregistered gates are in the
preregistration document. The exact runner command is:

```text
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m experiments.wildflower_dual_authority_0_2.run_dual_authority02 --seed 320
```

The runner rejects every other registered seed in this development package,
including the qualification candidates.

## Assumptions and credit

The reference store is the semantic oracle; the incremental store is the
implementation under test. The evaluator may use truth and transition labels
after mechanism mutation, but those values are excluded from the mechanism
input frame. Controls receive identical mechanism inputs and do not share
state.

## Verification gap

The package has not yet completed a valid fresh model seed run. The historical
311 run and the operationally failed 320-R1 run cannot validate 0.2. Predictive
H8 variance and independent-control superiority remain open. The 100,000
scaling harness is covered by the local harness but is not scientific evidence
until executed and recorded in a run artifact.

## Stop / continue

STOP before seed 320-R2. Review this report, the preregistration, the provenance
contract, the runner repair, and the run history. Seed 320-R2 was not executed
in this pass. Seeds 321, 322, 330, and 331 remain locked.

## Maturity

Prelock engineering evidence only. The successor is not scientifically
qualified and is not an architecture-success claim.

## Historical checkpoint

The frozen 0.1 checkout head is
`77d25c6a60ad1556d20ab5fbd82897f7b0e50fee`.

The archive manifest is
`experiments/WILDFLOWER_0_1_ARCHIVE_MANIFEST.sha256`.

## Source hashes

Hashes were captured after runner implementation and the final prelock
validation command. Documentation is not executable scientific input.
`successor/` paths below are relative to this 0.2 package directory.

```text
4651f3f62b40d0fd31fa3f6bd6b2d8109a79d3c3ffe60188cea62cfc38b633fc  successor/__init__.py
3c42de7f4cb759f0b1ad349cdff1c1db5b296f6dad85b8199c422ff61eea56e1  successor/controls.py
935e111cd0b600019f394d43d9a5f4f00eb5c3d2d747ab6957a19ee680150d47  successor/design.py
599cb592abc5974e3f314a52e873c4ca89b61142d3a0cc435cf5eccfde076ab9  successor/metrics.py
4df6523d301d99bae18d509e9994aa37ff12f9b4ecfa2de6a22df8c59197d401  successor/micro_simulations.py
cc9c71174035c0c438a7b55da1d769ec74c2d3cc44a7fa036912605151bec68e  successor/predictive_trace.py
c9ba63a29ce401ea874d0be5a6cd46a886010d809def9253b941b48ab6dae164  successor/qualification_guard.py
3746c58accd12d86aa5693d6e985a01e106cc58db83f562514231c773e49606e  successor/recorded_stream.py
818a9b3b7bbb9fd28211dca3d34fa41eec77d7cb328d769bde5d5d027f578fab  successor/run_dual_authority02.py
b2eb4d64c8dbc668ce9dd265b3178fd9d4071210255e27964cd587df88717de1  successor/scaling.py
24620c1ac16272c2ef3a30829e4e874631b4240a00e01f63a646976422800c49  successor/store.py
c09b902f7447a7d7adf89504dc75d1a179b343c28f7ed789f0a3d130e60aac06  successor/tests/test_controls.py
7de374650625dda18156fc1b0c9b762a1c057ed5cdd77465763210d4e46afdc8  successor/tests/test_prelock_interfaces.py
e63074d377f446e1bb76ae128feadfc7c75b428b63de63d6808e59692dd22f7e  successor/tests/test_provenance_contract.py
2860fa7ffa20cc83c84f2be7f6a512734dfd56ce1133e218bcae9df97369f01c  successor/tests/test_runner.py
af3ad372a15c9bf973d12edba19c9090fe8d4335aa602e03a41f43d960a0f917  WILDFLOWER_0_1_ARCHIVE_MANIFEST.sha256
```
