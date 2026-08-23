# Contributing to GRI Gauntlet

The project is intentionally strict about evidence because its purpose is to make post-hoc explanation harder, not easier.

## Basic development setup

```bash
git clone https://github.com/rbardyla-boop/gri.git
cd gri
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,research]'
```

Run the product regression suite with:

```bash
pytest \
  tests/test_gauntlet.py \
  tests/test_gauntlet_manipulations.py \
  tests/test_gauntlet_inspect_adapter.py \
  tests/test_gauntlet_autopsy.py \
  tests/test_gauntlet_claim_draft.py \
  tests/test_project_terminal_verdict.py
```

## Evidence rules

For changes that affect scientific or mechanism-credit claims:

1. Preserve the original evidence and terminal verdict.
2. Do not rewrite a failed experiment into a pass.
3. A repaired design is a new branch/gate, not a retroactive edit of the old result.
4. Pin external evidence to exact revisions/bytes where practical.
5. Distinguish retrospective audits from preregistered runs.
6. Keep candidate, baseline, metric direction, and negative-signal authority explicit.
7. If machine extraction is used, it must remain non-authoritative until the current human-approval boundary is deliberately changed and separately validated.
8. Add the strongest obvious baseline before claiming mechanism credit.
9. Prefer the narrowest claim supported by the evidence.
10. Preserve negative evidence when a simpler transparent method explains the result.

## Code rules

- Fail closed on malformed or ambiguous evidence.
- Do not introduce hidden network calls into core evaluation logic.
- Do not execute Markdown or foreign evidence as code.
- Treat experiment execution as trusted-code execution; do not describe Python audit hooks as an OS sandbox.
- Add regression tests for integrity/security boundary changes.
- Keep the distributable wheel limited to `gauntlet/` unless a package-boundary change is intentional and reviewed.

## External autopsy cases

A useful external case should have a precise credit target and enough public evidence to justify one of two outcomes:

- a narrow positive credit decision; or
- a specific reason credit must be withheld/unassessed.

Do not select external examples merely because they make Gauntlet look correct. Cases that expose a Gauntlet limitation are valuable evidence too.

## Pull requests

A pull request should state:

- what claim or product behavior changes;
- what does not change;
- the new or modified tests;
- whether evidence is retrospective or preregistered;
- any security/trust-boundary change;
- whether package/distribution bytes change.

CI should be green before merge. A green test suite is necessary but does not by itself authorize a broader scientific claim.
