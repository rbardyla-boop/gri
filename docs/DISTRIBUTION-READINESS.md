# GRI Gauntlet Distribution Readiness

Date: 2026-08-23

## Plain-English release target

The first release is **not** “AI that automatically decides whether research is true.”

The first release is:

> A local, fail-closed CLI that freezes evaluation evidence, checks replay/integrity boundaries, performs rule-bound mechanism-credit autopsies, and can turn a foreign Markdown comparison into a human-approved evidence record before the unchanged credit engine runs.

That scope is narrow enough to defend and useful enough to distribute for testing.

## Release state

```text
PRODUCT PACKAGE:              gri-gauntlet
PREFERRED CLI:                gri-gauntlet
LEGACY CLI ALIAS:             gauntlet
VERSION TARGET:               0.1.0
STATUS:                       FINAL HARDENING
PRODUCT-MARKET FIT:           NOT ESTABLISHED
AUTONOMOUS SCIENCE AUTHORITY: NO
LICENSE:                      APACHE-2.0
PUBLIC PACKAGE RELEASE:       BLOCKED UNTIL FINAL EXACT-BYTE CI + TAG
```

The distribution name deliberately uses `gri-gauntlet` because several unrelated projects already use “Gauntlet” as a package or product name. The shorter `gauntlet` command remains as a compatibility alias for the research repository, but public documentation should prefer `gri-gauntlet`.

## Scientific/product gates already passed

- Historical GRI/DMC/MCO terminal results remain preserved rather than rewritten.
- The generic mechanism-credit engine reproduces historical failure classifications.
- External AMB case: raw lead plus disclosed weak semantic comparator -> `STRONG_BASELINE_MISSING / WITHHELD`.
- External Embodied-Navigator controlled ablation -> `ADVANCE / PROVISIONAL`.
- External PRO-LONG lineage conflict -> `INTEGRITY_INVALID / UNASSESSED`.
- Human-gated foreign Markdown extraction reproduces the positive Embodied-Navigator disposition.
- Human-gated foreign Markdown extraction reproduces the negative AMB baseline-strength hold.
- Machine extraction remains non-authoritative before explicit content-bound human approval.
- Foreign Inspect AI logs are audited conservatively without inventing missing evidence.

These are retrospective mechanism-credit demonstrations, not independent reproductions of the external experiments.

## Distribution engineering gates

The release candidate must satisfy all of the following on the exact merge/tag commit:

1. **Source regression** — Gauntlet regression, manipulation, foreign-log, autopsy, claim-draft, and terminal-verdict tests pass.
2. **Wheel isolation** — the wheel contains `gauntlet/`, license, and distribution metadata only; historical DMC/GRI model packages are not shipped.
3. **Source-archive isolation** — the source distribution excludes historical artifacts, experiments, simulator code, model packages, and non-product tests.
4. **Build validation** — both wheel and source distribution build successfully and pass `twine check`.
5. **Fresh install** — the wheel installs into a new virtual environment with no undeclared runtime dependency.
6. **Python compatibility** — fresh-install smoke tests pass on Python 3.11, 3.12, and 3.13.
7. **CLI availability** — `gri-gauntlet`, legacy `gauntlet`, and `python -m gauntlet` report the same package version.
8. **Authority boundary** — a fresh-installed Markdown scan still returns `HUMAN_APPROVAL_REQUIRED` and does not infer a winner.
9. **Guard loading integrity** — target-project `src/gauntlet` shadowing cannot replace the installed guarded runner.
10. **Protected-path integrity** — common open/list/scandir/remove/rename operations against protected roots fail closed.
11. **Evidence-language accuracy** — locally frozen runs emit `FROZEN_RUN`; public preregistration is `NOT_ESTABLISHED` unless separately evidenced.
12. **Threshold semantics** — `minimum_improvement` is inclusive (`>=`).
13. **Security boundary documented** — subprocess mode is explicitly not a sandbox; Python audit-hook mode is explicitly not hostile-code containment.
14. **License bound** — Apache-2.0 exists in the repository and package metadata before public release.

All fourteen are now mechanical release gates. None may be waived merely to ship on schedule.

## Packaging boundary

The repository contains a large scientific history, but the product wheel intentionally includes only:

```text
gauntlet/
  __init__.py
  __main__.py
  cli.py
  core.py
  autopsy.py
  claim_draft.py
  _guard_exec.py
  adapters/...
```

The source distribution additionally contains the product README/license/security/contribution files, product examples, and Gauntlet-focused tests. Historical experiments and evidence remain available in the GitHub repository but are not copied into the product archive.

The package has no mandatory third-party runtime dependency. Historical research dependencies remain optional repository extras and are not required to use the distributed CLI.

## Security decisions made before release

A guarded Python experiment used to be launched after the target repository's `src/` directory had been placed on `PYTHONPATH`. A target project could therefore create its own `src/gauntlet/_guard_exec.py` and potentially shadow the installed guard.

The release candidate changes that boundary:

```text
isolated Python starts
        ↓
installed gauntlet._guard_exec loads
        ↓
Python audit hook installs
        ↓
target root/src paths become visible
        ↓
experiment entrypoint runs
```

A regression test places a hostile-name-collision `src/gauntlet/_guard_exec.py` in the target experiment and requires the real guard to remain authoritative while ordinary target imports continue to work.

The protected-root audit hook also blocks common filesystem metadata/mutation events on protected paths, not only ordinary file opens. This improves the experiment-integrity boundary but does **not** convert Python audit hooks into an operating-system sandbox.

## Evidence-language correction before release

A local freeze demonstrates that exact configuration/input bytes were bound before the corresponding Gauntlet run and can be replay-checked. That is useful evidence, but it is not enough to establish that hypotheses or thresholds were publicly preregistered before results were observed.

Therefore the 0.1.0 machine evidence class is:

```text
FROZEN_RUN
```

and the verdict explicitly records:

```text
public_preregistration: NOT_ESTABLISHED
```

External preregistration evidence can be added later as a separate evidence source rather than inferred from a local freeze.

## Known limitations accepted for 0.1.0

These are not release blockers if they remain explicit:

- Mechanism-credit extraction is currently Markdown-table oriented, not arbitrary PDF/paper understanding.
- Human approval is required for candidate/baseline selection and source-backed negative signals.
- External demonstrations are retrospective and depend on author-published evidence.
- `run.mode = "subprocess"` executes trusted commands with user permissions and is not sandboxed.
- `run.mode = "python"` uses Python audit hooks and is not an OS-level hostile-code sandbox.
- Freeze manifests currently contain local filesystem root information; users should review artifacts before public sharing.
- No customer-demand or willingness-to-pay evidence exists yet.
- No durable-moat claim is justified yet.

## License decision

**Apache License 2.0** is selected for `gri-gauntlet` 0.1.0.

Reasons for the selection:

- permissive use and redistribution;
- explicit patent grant;
- standard open-source tooling compatibility;
- no requirement to open-source unrelated downstream applications merely because they use Gauntlet.

The license selection does not imply warranty, scientific endorsement, or trademark permission beyond the license terms.

## Distribution plan

### Stage 1 — GitHub beta

After all final hardening gates are green:

1. merge `gauntlet-0.1.0-final-hardening` into `main`;
2. rerun all required CI on the merge commit;
3. create tag `v0.1.0` on that exact proven commit;
4. create a GitHub release containing the exact release notes and commit/tag identity;
5. attach or reproducibly build the wheel and source distribution;
6. publish the SHA-256 hashes of those files;
7. recommend installation with an isolated tool environment such as `uv tool` or `pipx` where available;
8. invite a small number of external users to run the included examples and file reproducibility/usability issues.

### Stage 2 — PyPI beta

Do this only after the GitHub beta can be installed and reproduced by someone other than the builder.

1. confirm the distribution name `gri-gauntlet` is available at publication time;
2. configure PyPI Trusted Publishing for this GitHub repository rather than storing a long-lived upload token;
3. publish only from a tagged GitHub release whose CI is green;
4. make `gri-gauntlet` the documented command;
5. keep `gauntlet` only as a compatibility alias and clearly note possible command-name collisions.

### Stage 3 — External proof

The next scientific/product evidence should come from people or repositories that were not used to design the current gates.

Minimum useful external beta target:

- at least 3 independent users or teams;
- at least 10 claim/evaluation audits not authored by this project;
- record whether Gauntlet changed a claim, caught an integrity problem, or merely added paperwork;
- record false alarms and cases where the human approval burden is too high;
- compare time-to-audit against ordinary manual review;
- do not optimize the success metric after seeing these results.

The release remains a research alpha/beta until this external-use evidence exists.

## Stop conditions

Do not add dashboards, hosted services, agent swarms, automatic LLM judges, or expensive infrastructure merely to make the project look larger.

Stop or narrow the product if external users show that:

- the mechanism-credit decisions do not change real research decisions;
- the human approval burden costs more than the errors it prevents;
- existing tools provide the same result with materially less work;
- generic extraction introduces too many false evidence links;
- users primarily want ordinary experiment tracking rather than mechanism-credit analysis.

## Release authority

Public release is authorized only when the final hardening branch is merged and the exact resulting `main` commit passes the full release gates above. The tag and attached hashes must identify those final bytes. No later code change inherits that authorization automatically.
