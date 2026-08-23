# TE0 Current State — 2026-08-23

## State

```text
UNIT:                       TE0 — Tool Ecology Sandbox
BRANCH:                     forge-sandbox-v0
STATUS:                     DEVELOPMENT / PRE-SCIENCE
SCIENTIFIC MODEL CALLS:     0
SCIENTIFIC VAULT RUNS:      0
DURABLE SKILL AUTHORITY:    0
MAIN MERGE:                 NOT AUTHORIZED
```

## Implemented

- typed allow-listed tool registry;
- bounded Toolsmith composition search;
- explicit failure classification;
- declarative ToolSmith with no arbitrary code execution;
- NullSmith simple controls;
- Composer complexity/cost penalties;
- Grinder fixed-candidate mutation testing;
- single-tool ablation;
- one-shot Judge with burn-before-score Vault marker;
- hash-bound Judge receipts;
- append-only hash-chained ledger;
- skill-packet promotion requiring Judge PASS;
- rootless Podman/Docker local sandbox launcher with network disabled and repository mounted read-only;
- public TE0-E0 qualification fixture.

## Safety / integrity boundary

ToolSmith v0 cannot generate Python or shell code. Its allow-listed DSL contains only pure transparent operations. The local container sandbox is defense in depth, not the authority boundary. Frozen project artifacts and hidden Vault data remain outside the development search surface.

## Failure-learning rule

A failure is first classified as one of:

`INTEGRITY / RESOURCE / MEASUREMENT / INTERFACE / TASK_DEFINITION / RETRIEVAL / STATE / TOOL / MODEL / UNKNOWN`.

Tool generation is permitted only when a tool-level repair is scientifically meaningful. Resource, integrity, or unqualified-instrument failures must be repaired at their own layer rather than hidden by a better recipe.

## First qualification target

TE0-E0 is deliberately non-scientific. It tests whether the machinery can rediscover a known multi-tool normalization repair from BUILD/DEV and survive a one-shot public test Vault. It exists to qualify the pipeline, not to provide evidence about a model or architecture.

## Advancement gate

Do not run a scientific TE0 experiment until all exact-head CI gates are green and the first hidden target, claim, BUILD/DEV/Vault partition, threshold, resource budget, and one-run Judge authorization are frozen in a separate preregistration.
