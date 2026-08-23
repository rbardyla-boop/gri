# TE0 — Tool Ecology Sandbox

Status: **ENGINEERING RESEARCH PROTOCOL — NOT SEMANTIC SCIENCE**

## Claim under test

> A frozen local model can discover and retain useful external tool recipes through disposable search, while an independent verifier prevents failed or overfit recipes from becoming durable authority.

TE0 does not test consciousness, semantic understanding, personhood, AGI, or human equivalence.

## Fixed core

The base model is treated as frozen during a TE0 generation. Model weights are not modified by ToolSmith, Composer, Grinder, or Judge.

## Components

1. **ToolSmith** — creates candidate tools from explicit contracts.
2. **Composer / Recipe Search** — searches combinations of promotable tools.
3. **Grinder** — repeatedly attacks candidate adapters/recipes on BUILD/DEV synthetic fixtures.
4. **Judge** — one-shot independent verifier on hidden VAULT fixtures.
5. **Ledger** — append-only record of experiments, hashes, failures, costs and authority state.
6. **Sandbox** — disposable local execution with network disabled by default and bounded resources.

Supporting components:

- Fixture Forge — creates non-semantic synthetic tasks.
- Pool Forge — deterministically partitions BUILD / DEV / VAULT.
- Failure Classifier — localizes failures before ToolSmith invents a repair.
- Freeze Gate — binds the winning engineering stack before any future scientific instrument uses it.

## Visibility firewall

Candidate tools receive only:

- fixture ID;
- fixture kind;
- prompt;
- non-gold state produced by previous tools.

They never receive target/gold values.

BUILD may be used by ToolSmith, Composer and Grinder.
DEV may be used repeatedly by Composer and Grinder.
VAULT may be opened only by Judge after a one-shot authorization binds the recipe, tool catalog, pool manifest, VAULT hash and thresholds.

## Tool protocol

Every recipe tool receives JSON on stdin:

```json
{
  "fixture": {"id": "...", "kind": "...", "prompt": "..."},
  "state": {}
}
```

Every tool must return exactly:

```json
{"state": {}}
```

The final recipe state must contain `prediction`.

A tool may add working state such as retrieval packets, bounded memory, raw model candidates, parsed candidates, confidence or comparison results. It may not add hidden gold.

## Recipe search

Default search:

- depth 1;
- retain best 8;
- expand to depth 2;
- retain best 8;
- expand to depth 3;
- stop if objective improvement disappears.

The engineering objective penalizes:

- structural failures;
- wrong outputs;
- additional tools;
- latency.

Future versions may add token, VRAM and energy penalties.

Complexity must earn its place. A six-tool recipe that performs effectively the same as a two-tool recipe loses.

## Failure localization

Before generating a repair, failures should be classified as one of:

- MODEL_FAILURE
- MEASUREMENT_FAILURE
- TOOL_FAILURE
- RETRIEVAL_FAILURE
- STATE_FAILURE
- INTERFACE_FAILURE
- RESOURCE_FAILURE
- TASK_DEFINITION_FAILURE
- UNKNOWN_FAILURE

ToolSmith must be allowed to conclude that no new tool is indicated.

## Grinder attacks

The Grinder/fixture ecosystem should progressively include:

- exact replay;
- candidate-order reversal;
- paraphrase;
- distractors;
- missing information;
- contradictory information;
- framing changes;
- multiple seeds;
- malformed tool output;
- tool timeout/unavailability;
- wrong retrieval packets;
- resource pressure;
- semantically equivalent output variants where the evaluator explicitly supports equivalence.

## Promotion

A candidate recipe has no durable authority because it wins BUILD or DEV.

Promotion requires:

1. frozen recipe hash;
2. frozen tool hashes/catalog;
3. frozen VAULT hash;
4. preregistered Judge thresholds;
5. one-shot Judge authorization consumed before VAULT item 1;
6. Judge PASS;
7. Ledger record with `authority=true` bound to Judge result.

A failed Judge result is terminal for that authorized recipe. Retuning after a VAULT failure requires a new recipe generation and, preferably, a fresh VAULT generation.

## Recommended first TE0 target

Use a failure class already understood but reproduce it with fresh synthetic fixtures. Do not reuse retired SEM benchmark cases.

The first target should test whether the ecology can discover a robust interface recipe for exact structured copying / mapping under perturbation.

A successful result would show that the engineering system can discover a recipe that survives hidden synthetic validation without modifying model weights. It would not establish semantic understanding.

## End-state relationship to Meaning Before Mind

The intended sequence is:

`TE0 engineering -> freeze reliable tool ecology -> create a fresh semantic instrument -> preregister -> one scientific run -> score`

TE0 is therefore part of measurement engineering, not evidence for the later semantic hypothesis.
