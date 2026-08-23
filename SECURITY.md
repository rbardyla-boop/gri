# Security and Trust Boundaries

GRI Gauntlet is an evaluation-integrity tool, not a general-purpose malware sandbox.

## Supported release

The current public target is the `0.1.x` research-alpha line. Security-relevant fixes should be applied to the latest `0.1.x` release candidate before wider distribution.

## Critical trust boundary: experiment execution

Gauntlet can execute experiment code. Treat experiment specifications and entrypoints as code with the same trust level as running them directly on your machine.

### `run.mode = "subprocess"`

This mode runs the declared command with the current user's operating-system permissions.

It provides hashing, binding, receipts, replay bookkeeping, and result gates. It does **not** claim filesystem, network, process, container, or privilege isolation.

Do not run an untrusted subprocess-mode specification merely because it is wrapped by Gauntlet.

### `run.mode = "python"`

Python mode can install a Python audit hook before running the declared entrypoint. Depending on the frozen policy it can block access to declared protected roots, subprocess creation, and network connections visible through the audited Python operations.

The guard is launched with Python isolated mode before target-project import paths are exposed. This prevents a target repository's `src/gauntlet` package or inherited `PYTHONPATH` from replacing the installed guard during launch.

This remains a **Python-level integrity guard, not hostile-code containment**. Native extensions, interpreter vulnerabilities, operating-system interfaces not covered by the audit policy, or other adversarial techniques are outside the current containment claim. Use an actual container/VM/sandbox when executing code you do not trust.

## Foreign Markdown ingestion

`draft-markdown` parses Markdown as data and does not execute embedded code blocks.

Machine extraction has no scientific decision authority. It may catalog tables and unresolved evidence requests, but it does not choose the candidate, baseline, metric direction, negative signal, or credit disposition.

`approve-markdown` requires a human-authored approval artifact bound to the exact scanned source bytes/revision. Source-backed facts must cite text that is present in the bound source. If the source changed or the selected evidence cannot be verified, materialization fails closed.

Approval artifacts are authority-bearing research records. Review them like code before committing or sharing them.

## Files and privacy

Gauntlet receipts fingerprint stdout/stderr rather than storing their full content, but manifests and evidence artifacts may still contain:

- local filesystem paths;
- repository commit identifiers;
- command arguments;
- names of input/output files;
- selected source text or external source URLs.

Review artifacts before publishing them if local paths or source metadata are sensitive.

Do not place API keys, passwords, tokens, private keys, or other secrets in experiment specifications, approval artifacts, committed fixtures, or command arguments.

## Dependency surface

The distributable `gri-gauntlet` wheel intentionally contains only the `gauntlet` Python package. Historical GRI/DMC/MCO research modules and their heavier dependencies are excluded from the product wheel.

The core Gauntlet package currently has no mandatory third-party runtime dependency.

## Reporting a vulnerability

For non-sensitive defects, use the repository issue tracker.

Do not post working exploit details, credentials, or private data in a public issue. If a vulnerability requires confidential handling and no private GitHub security-reporting channel is available, contact the repository owner through GitHub before disclosing exploit details publicly.

## Security non-claims

A green Gauntlet result does not prove that:

- arbitrary experiment code is safe to execute;
- the operating system is isolated;
- external evidence is truthful;
- a benchmark is valid for every real-world use;
- a human approval decision is correct;
- an AI system is generally safe.

Gauntlet's security objective is narrower: make evaluation evidence boundaries, integrity checks, and claim-credit decisions explicit and fail closed when the registered evidence is insufficient.
