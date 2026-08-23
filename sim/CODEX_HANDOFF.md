# Codex Handoff — GRI-SIM-0

You are working inside the Small-Info / GRI research project.

## Authority

GRI-SIM-0 is testing infrastructure only. No successor GRI mechanism is authorized by this handoff.

## Read-only files

Treat these as immutable during a candidate task:

- `gri_sim0.py`
- `candidate_protocol.py`
- `experiment_manifest.json`
- any frozen fixture bank
- any frozen operation rules
- any frozen verdict logic
- parent/control implementations and receipts

## Writable scope

Only modify a candidate-specific directory explicitly named by the task:

```text
experiments/candidates/<authorized-candidate-id>/
```

Candidate work must contain:

- candidate source;
- candidate manifest;
- candidate-specific tests;
- source/config hashes.

## Hard boundaries

Do not add:

- hidden counters;
- history buffers;
- task ids;
- fixture ids;
- label access during evaluation;
- delay or sequence-position inputs;
- undeclared lookups/caches;
- post-result threshold changes;
- post-result optimizer changes;
- new mechanism after the first frozen result.

Every comparison/branch/lookup/copy/nonlinearity must be accounted under the frozen operation rules. A semantic selector implemented inside candidate code is candidate cost.

## Development versus science

Development smoke may be repeated and must be labeled `DEV_SMOKE`.

A frozen scientific run requires a separate authorization naming the candidate, frozen source/config hashes, independent accounting audit, deterministic replay, and no post-result tuning.
