# MBM Bench Shop

Status: **ENGINEERING LAB — NEVER SCIENTIFIC EVIDENCE**

This directory is deliberately outside the retired SEM-0/SEM-0R/SEM-0R2/SEM-0R3 execution lineage.

## Purpose

Build and abuse-test the measurement machinery for future *Meaning Before Mind* experiments before any semantic benchmark is exposed.

The lab may freely optimize:

- transport adapters;
- output representations;
- constrained-decoding strategies;
- prompts used for serialization/instruction-following only;
- parsers and canonicalizers;
- sandbox policies;
- retry/error-reporting policy for engineering tests;
- tool combinations.

The lab must **not** read or use semantic benchmark cases, semantic gold labels, family designations, or future hidden holdouts.

## Architecture

`fixture_forge.py` creates synthetic, non-semantic stress fixtures covering exact copying, enum selection, keyed mappings, set membership, ordered vectors, long-ID retention, distractors, and deliberate malformed-output traps.

`grinder.py` repeatedly runs candidate adapters against those fixtures, records every raw response, calculates structural reliability, exact mapping accuracy, determinism, latency and failure class, and ranks protocol configurations. It is allowed to grind until the engineering stack is reliable because none of its fixtures are scientific evidence.

`toolsmith.py` is the tool-making tool. A small JSON contract describes a command-line adapter and its capabilities; Toolsmith validates the contract and emits a runnable adapter skeleton plus a smoke test. New adapters therefore enter the grinder through the same interface rather than ad-hoc code.

`sandbox_exec.py` runs arbitrary adapter commands inside a local Linux sandbox. It prefers rootless Podman, can use Bubblewrap, disables network by default, limits CPU/memory/processes where the backend supports it, and writes an execution receipt.

`freeze_gate.py` hashes the selected adapter, lab configuration and reliability report into an immutable engineering manifest. A future scientific project should bind that manifest before its benchmark is generated/finalized.

## Recommended protocol candidates

1. Ollama JSON mode — negative control because SEM-0R already showed that syntactic JSON is insufficient.
2. Ollama JSON Schema structured output.
3. One proposition per request: label enum only; evidence measured separately.
4. Fixed-order label vector: the harness supplies proposition IDs so the model never copies IDs.
5. Evidence as one binary decision per `(proposition, context statement)`; the harness supplies both IDs and the model answers only `YES`/`NO`.
6. `llama.cpp` grammar/JSON-schema constrained decoding, ideally with LLGuidance where available.
7. Hybrid: constrained label call + separate binary evidence calls.

The preferred scientific interface is the simplest candidate that makes malformed output practically impossible. A wrong `YES`, `NO`, or label should become a scientific error instead of an integrity crash.

## Grinder promotion gates

Before an adapter can be frozen for future science, recommended minimums are:

- >= 10,000 synthetic decisions;
- zero unparseable/structurally invalid responses in the final stress run;
- >= 0.999 exact serialization/mapping accuracy on pure copy fixtures;
- exact replay >= 0.999 under fixed seeds;
- zero hidden use of SEM/future benchmark paths;
- raw-response provenance for every failure;
- successful fault-injection tests;
- a frozen adapter hash and configuration hash.

These are engineering gates, not scientific thresholds.

## Scientific firewall

The development cycle is:

`synthetic fixtures -> tool forge -> sandbox -> grinder -> failure minimizer -> protocol selection -> freeze engineering stack`

Only after that:

`new hidden semantic instrument -> preregistration -> one scientific execution -> score`

Never feed a scientific failure back into the grinder. If future science reveals a new interface weakness, that scientific version remains terminal and the next study begins from a separately named engineering cycle.
