# GRI Gauntlet 0.1.0 Final-Hardening State — 2026-08-23

## Status

```text
PRODUCT:                       GRI Gauntlet
DISTRIBUTION:                  gri-gauntlet
VERSION:                       0.1.0
BRANCH:                        gauntlet-0.1.0-final-hardening
EXACT PROVEN HEAD:             e1e623cbbe925a0a7da758cde8167ab4c30ed757
LICENSE:                       Apache-2.0
TECHNICAL RELEASE GATES:       PASS
PUBLIC GITHUB BETA:            AUTHORIZED AFTER MERGE OF THESE BYTES
PYPI:                          NOT YET AUTHORIZED
PRODUCT-MARKET FIT:            NOT ESTABLISHED
AUTONOMOUS SCIENCE AUTHORITY:  NOT CLAIMED
```

This record supersedes the earlier license-blocked release-candidate state for release decisions. It does not alter or reopen any historical GRI/DMC/MCO scientific verdict.

## Final defects closed

The post-merge source audit found and closed four concrete release defects:

1. `minimum_improvement` was implemented with strict `>` rather than inclusive `>=`.
2. protected Python roots were guarded mainly at file-open time rather than against common metadata/mutation operations.
3. local frozen runs were labeled `PREREGISTERED_RUN`, which overstated what a local freeze proves.
4. the source distribution included unnecessary historical research/test material even though the wheel itself was clean.

The final-hardening branch changes these to:

```text
minimum_improvement       -> inclusive >=
protected-path operations -> open/list/scandir/remove/rename and related audited operations blocked
local run evidence        -> FROZEN_RUN
public preregistration    -> NOT_ESTABLISHED unless separately evidenced
source archive            -> product-scoped
license                   -> Apache-2.0
```

## Exact CI

All release-relevant workflows passed on exact head:

```text
e1e623cbbe925a0a7da758cde8167ab4c30ed757
```

### Gauntlet Rescue

```text
workflow run: 32645407284
result:       PASS
```

This includes:

- Gauntlet core regression tests;
- manipulation/security tests;
- foreign Inspect AI audit tests;
- mechanism-credit autopsy tests;
- Markdown claim-draft/approval tests;
- historical terminal-verdict preservation;
- retrospective MCO-05 self-audit;
- external AMB/Embodied-Navigator/PRO-LONG discriminators;
- semi-automatic human-approved Markdown positive case;
- frozen end-to-end run/replay/verdict;
- real Inspect AI foreign-log generation and audit.

The frozen demo now mechanically requires:

```text
evidence_class:          FROZEN_RUN
public_preregistration:  NOT_ESTABLISHED
```

### External negative gate

```text
workflow run: 32645407316
result:       PASS
```

The pinned Agent Memory Benchmark path still produces the intended strong-baseline hold through the generic human-approved workflow.

### Distribution Readiness

```text
workflow run: 32645407253
result:       PASS
```

Passed jobs:

```text
source-regression
wheel-smoke-py3.11
wheel-smoke-py3.12
wheel-smoke-py3.13
```

For each supported Python version the workflow:

- builds wheel and source archive;
- runs `twine check`;
- verifies product-only wheel contents;
- verifies the source archive excludes historical artifacts/experiments/model packages/non-product tests;
- verifies Apache license presence;
- installs into a fresh environment outside the repository;
- runs `pip check`;
- checks all CLI entry paths;
- runs a standalone Markdown draft smoke test.

## Final branch artifact

GitHub Actions artifact:

```text
name:           gri-gauntlet-dist
artifact id:    9494728421
workflow run:   32645407253
head commit:    e1e623cbbe925a0a7da758cde8167ab4c30ed757
archive digest: sha256:62564385ff7604aa410b6b8a47b13db42693256420634df7422dd35b1274333e
```

Artifact files and independently rechecked SHA-256 values:

```text
bcd97251af4e39fee902c2f91bff6e05e2f9023ec313dcc74e17f80125a9ec15  gri_gauntlet-0.1.0-py3-none-any.whl
b8d0d96b74af4ef228481f50eaffad0b7329e491149e7406b1378dc06a847c25  gri_gauntlet-0.1.0.tar.gz
```

The downloaded artifact's `SHA256SUMS` contains the same two values exactly.

## Security boundary

The 0.1.0 Python guard is an experiment-integrity mechanism, not an operating-system hostile-code sandbox.

The guarded launch remains:

```text
python -I
 -> trusted installed gauntlet._guard_exec
 -> audit hook installed
 -> target root/src made importable
 -> experiment entrypoint
```

Regression tests also require protected-root list/scandir/remove/rename attempts to fail closed without moving or deleting the protected file.

Subprocess mode continues to execute trusted commands with the user's permissions and makes no containment claim.

## Scientific-language boundary

`FROZEN_RUN` means the run is bound to exact local specification/input evidence under Gauntlet's freeze and replay machinery.

It does not mean:

- public preregistration timing is proven;
- holdout isolation is universally proven outside the guarded boundary;
- external author-reported measurements are independently reproduced;
- an `ADVANCE` outcome establishes general architecture superiority.

Those require separate evidence.

## Release authority

If this exact proven branch is merged without content changes, the resulting identical tree is authorized for the **GitHub 0.1.0 research-alpha beta**.

After merge:

1. verify the resulting `main` tree is identical to this proven tree;
2. allow the configured `main` CI workflows to rerun;
3. tag the exact merge/main commit `v0.1.0` only if no content change occurred;
4. create a GitHub release with these limitations and final rebuilt artifact hashes;
5. begin external beta collection.

PyPI remains deliberately gated on at least one independent external installation/reproduction. Product-market-fit and commercial-superiority claims remain unauthorized.
