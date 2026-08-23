# SEM-0R3 — Object-Keyed Evidence Replication Protocol

Status: **PRE-SCIENCE SUCCESSOR DESIGN**

Parent semantic instrument: SEM-0R frozen manifest record SHA-256 `bdbb5f774ec36e444e9bd147cae770554330431aa68b444fb25650cbbcea2d96`.

Prior executions:

- SEM-0R RUN-001: `INTEGRITY_INVALID` at LIVE ordinal 2 (`prediction_3_invalid_label`).
- SEM-0R2 RUN-001: `INTEGRITY_INVALID` at LIVE ordinal 15 (`prediction_3_duplicate_evidence`).

Neither prior execution is retried, continued, rescored, or interpreted as a semantic-control pass/fail result.

## Frozen semantic content

SEM-0R3 preserves without modification the SEM-0R cases, gold, replay set, context-ablation set, pair designations, semantic families, thresholds, baseline report, scorer, candidate model identity, historical model blob, Ollama 0.21.2 runtime, temperature, and deterministic seed basis.

## Reason for successor

SEM-0R2 showed that JSON-schema generation constrained the registered label enum but did not reliably enforce `uniqueItems` for evidence arrays. Because the registered evidence object is semantically a set of opaque context-statement IDs, SEM-0R3 changes only the wire representation so duplicate membership cannot be expressed as an array artifact.

## Wire representation

The model returns a JSON object whose `predictions` value is itself an object keyed by registered proposition ID. Each proposition object contains:

- `label`: one registered label;
- `evidence`: an object keyed only by registered context-statement IDs, with boolean values.

For example:

```json
{
  "predictions": {
    "P1": {
      "label": "ENTAILED",
      "evidence": {"S1": true, "S2": true}
    }
  }
}
```

The runner deterministically translates the wire representation into the unchanged SEM-0R parent payload:

```json
{
  "predictions": [
    {"proposition_id": "P1", "label": "ENTAILED", "evidence": ["S1", "S2"]}
  ]
}
```

Only evidence keys whose value is exactly `true` are included. Proposition and evidence ordering in the translated payload follows the frozen case ordering. No semantic inference, aliasing, spelling repair, label repair, fuzzy matching, deduplication, or threshold change is permitted.

## Duplicate-key defense

The inner model JSON is parsed with duplicate-object-key detection. Repeated JSON keys terminate the run rather than being silently collapsed by the standard parser.

## Interface qualification

Before scientific authorization, the exact model/runtime must pass a non-benchmark serialization-only qualification that specifically tests:

- multiple proposition keys;
- multiple evidence keys for a proposition;
- empty evidence membership;
- the six-label enum;
- deterministic wire-to-parent translation;
- no duplicate object keys;
- raw-response persistence.

Qualification exposes no SEM-0R benchmark content and produces no semantic evidence.

## Authorization and execution

SEM-0R3 requires a new one-run authorization bound to the frozen SEM-0R manifest, exact model identity, frozen full/replay/ablation inputs, frozen baseline report, interface-qualification record, and exact SEM-0R3 source hashes.

Authorization is consumed before scientific request #1. A crash still spends it. There is no per-case retry.

## Gold boundary and terminal outcomes

The original order remains:

`LIVE -> seal -> REPLAY -> seal -> CONTEXT_ABLATION -> seal -> open GOLD -> score once`

Terminal classifications remain:

- `SEMANTIC_CONTROL_GATE_PASS`
- `SEMANTIC_CONTROL_GATE_FAIL`
- `INTEGRITY_INVALID`

Any SEM-0R3 publication must disclose both earlier integrity-invalid attempts and this post-failure interface change.
