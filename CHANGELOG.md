# Changelog

All notable changes to the distributable `gri-gauntlet` package are recorded here.

## 0.1.0 — release candidate

### Added

- Fail-closed experiment freeze, verify, run, replay, and verdict workflow.
- Retrospective result audit that is explicitly distinguished from frozen-run and preregistration evidence.
- Generic mechanism-credit autopsy with fixed precedence for invalidating and positive signals.
- Conservative Inspect AI JSON log audit.
- Generic Markdown comparison-table scanner with no automatic credit authority.
- Content-bound human approval step for candidate/baseline/metric selection.
- Source-backed approved facts and negative mechanism-credit signals.
- Evidence-request checklist for baseline strength, model/budget/data parity, ablation isolation, source lineage, and replication.
- External retrospective discriminator cases covering provisional credit, withheld credit, and unassessed credit.
- Clean Python wheel containing only the `gauntlet` product package.
- Preferred `gri-gauntlet` CLI plus legacy `gauntlet` compatibility alias.
- Apache License 2.0 distribution license.

### Security and integrity

- Guarded Python runs load the installed Gauntlet guard in Python isolated mode before target-project import paths are exposed.
- Added a regression test proving a target repository's `src/gauntlet/_guard_exec.py` cannot shadow the installed guard.
- Protected Python paths now reject common metadata and mutation operations such as list/scandir/remove/rename, in addition to file opens.
- Explicitly documented that subprocess mode is not sandboxed and Python audit-hook mode is not hostile-code containment.
- Frozen verdicts now emit `FROZEN_RUN`, not `PREREGISTERED_RUN`; public preregistration remains explicitly `NOT_ESTABLISHED` unless separately evidenced.
- Human-approved `minimum_improvement` thresholds are inclusive (`>=`) rather than accidentally strict (`>`).

### Distribution validation

- Wheel and source distribution build through standard Python packaging.
- `twine check` passes.
- Fresh wheel installation and CLI smoke tests pass on Python 3.11, 3.12, and 3.13.
- Historical research packages are excluded from the product wheel.
- The source archive is explicitly scoped away from historical artifacts, experiments, model packages, and non-product tests.
- Core product has no mandatory third-party runtime dependency.

### Boundaries

- Research alpha: product-market fit is not established.
- Foreign external cases are retrospective and are not independent reproductions.
- Machine extraction does not become scientific authority.
- A local freeze does not by itself establish public preregistration timing.
