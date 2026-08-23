# GRI Gauntlet 0.1.0 Release-Candidate State — 2026-08-23

## Status

```text
PRODUCT:                         GRI Gauntlet
DISTRIBUTION NAME:               gri-gauntlet
VERSION:                         0.1.0
MATURITY:                        RESEARCH ALPHA / RELEASE CANDIDATE
PRE-MERGE CANDIDATE COMMIT:      b05be8b3c62bad465519b43a18a21a23a35eadf5
TECHNICAL RELEASE GATES:         PASS
PUBLIC PACKAGE LICENSE:          NOT SELECTED
PUBLIC PACKAGE PUBLICATION:      BLOCKED ON LICENSE DECISION
PRODUCT-MARKET FIT:              NOT ESTABLISHED
AUTONOMOUS SCIENCE AUTHORITY:    NOT CLAIMED
```

This record freezes the technical release-candidate evidence before merge. It
does not alter any prior GRI/DMC/MCO scientific result and does not convert
retrospective external audits into independent reproductions.

## Exact clean CI on the candidate

All three release-relevant workflows passed on exact commit:

```text
b05be8b3c62bad465519b43a18a21a23a35eadf5
```

### Gauntlet Rescue

```text
workflow run: 32638553053
result:       PASS
```

This includes the product regression/manipulation/autopsy/claim-draft suite,
historical terminal-verdict preservation, retrospective MCO-05 self-audit,
historical mechanism-credit autopsies, external AMB/Embodied-Navigator/
PRO-LONG gates, the positive human-gated Markdown path, frozen end-to-end replay,
and a real Inspect AI foreign-log audit.

### Semi-automatic external negative gate

```text
workflow run: 32638553142
result:       PASS
```

The generic Markdown workflow downloads the pinned Agent Memory Benchmark
README, verifies its exact Git blob, leaves baseline strength unresolved before
human approval, then uses a content-bound approval record to reproduce:

```text
ADVANCE:                   TRIGGERED
STRONG_BASELINE_MISSING:   TRIGGERED
FINAL:                     STRONG_BASELINE_MISSING / CREDIT WITHHELD
```

No AMB-specific decision code is present in the generic credit engine.

### Distribution Readiness

```text
workflow run: 32638553162
result:       PASS
```

Passed jobs:

```text
source-regression
wheel-smoke-py3.11
wheel-smoke-py3.12
wheel-smoke-py3.13
```

For each supported Python version the workflow builds the distribution, runs
`twine check`, verifies wheel package isolation, creates a fresh virtual
environment outside the repository, installs the wheel, runs `pip check`, checks
all three CLI entry paths, and runs a standalone Markdown draft smoke test.

## Distribution artifact

GitHub Actions artifact:

```text
name:          gri-gauntlet-dist
artifact id:   9492968958
workflow run:  32638553162
head commit:   b05be8b3c62bad465519b43a18a21a23a35eadf5
archive digest: sha256:02cd9029b48bb5c7b47e049e2a7751908530bddaa396722a12de5747f8f60991
```

The artifact contains:

```text
gri_gauntlet-0.1.0-py3-none-any.whl
gri_gauntlet-0.1.0.tar.gz
SHA256SUMS
```

The generated manifest records:

```text
0aed57efa55bb5b3e695888af0e7553bdea9c9537f9b8499bde79096bf329069  gri_gauntlet-0.1.0-py3-none-any.whl
9369546ed467886a6cdd6f8d0d4d0b8226f93956d3cc2f03670876aad9e14b39  gri_gauntlet-0.1.0.tar.gz
```

The two files were independently re-hashed after downloading the CI artifact;
both matched `SHA256SUMS` exactly.

## Security repair included in the candidate

A pre-release audit found that guarded Python runs previously launched after the
target repository's `src/` path had been inserted into `PYTHONPATH`. A target
repository could therefore create a name-collision package at
`src/gauntlet/_guard_exec.py` and potentially replace the intended guard during
module launch.

The release candidate changes the boundary to:

```text
python -I
   -> load installed gauntlet._guard_exec
   -> install Python audit hook
   -> add target repository/root import paths
   -> run target experiment entrypoint
```

The environment also removes inherited `PYTHONPATH` for guarded Python launch.
A regression test creates a fake target `src/gauntlet/_guard_exec.py`, verifies
that it is not executed, and simultaneously verifies that ordinary target
`src/` imports continue to work.

This passed the exact release-candidate workflows above.

## Package boundary

The distributable wheel contains the `gauntlet` product package and distribution
metadata only. Historical GRI/DMC/MCO modules are deliberately excluded from the
wheel and remain repository research evidence.

The core package has no mandatory third-party runtime dependency.

Preferred public command:

```text
gri-gauntlet
```

Compatibility command:

```text
gauntlet
```

Module entry:

```text
python -m gauntlet
```

## External mechanism-credit evidence frozen before release

The same generic engine has demonstrated these disjoint retrospective outcomes:

```text
Agent Memory Benchmark
large lead + explicitly weak semantic comparator
-> STRONG_BASELINE_MISSING / WITHHELD

Embodied-Navigator
controlled matched-policy memory ablation + positive deltas
-> ADVANCE / PROVISIONAL

PRO-LONG
matched-budget positive lead + unresolved source lineage
-> INTEGRITY_INVALID / UNASSESSED
```

The human-gated generic Markdown path has independently reproduced both the
positive Embodied-Navigator disposition and the negative AMB baseline-strength
disposition without placing experiment-specific decision rules into the engine.

## Distribution decision boundary

The software is technically ready for a **GitHub beta/release candidate** once
merged and revalidated on `main`.

A public package release is deliberately blocked because the repository has no
explicit license. Choosing a license changes the legal rights granted to other
people and is therefore an owner decision, not an engineering default.

The release process after that decision is already specified in
`docs/DISTRIBUTION-READINESS.md`:

```text
select explicit license
-> update package metadata
-> rerun exact CI on final bytes
-> tag v0.1.0
-> GitHub release + hashes
-> external beta
-> PyPI via Trusted Publishing only after external install/reproduction
```

## Remaining non-blocking scientific/product unknowns

These do not block a research-alpha GitHub beta, but they prevent stronger
commercial claims:

- customer demand and willingness to pay are not established;
- independent external usability is not established;
- current claim extraction is Markdown-table oriented rather than arbitrary
  paper/PDF understanding;
- human approval burden may prove too high;
- no durable moat has been established;
- Python guarded mode is not an operating-system hostile-code sandbox;
- subprocess mode is trusted-code execution with the user's permissions.

## Mechanical next action

Merge the release-candidate branch only after the final branch-head workflows
remain green. Then rerun/verify the required workflows on the resulting `main`
commit. Do not create `v0.1.0` and do not publish a package until an explicit
license has been selected and bound into the final release bytes.
