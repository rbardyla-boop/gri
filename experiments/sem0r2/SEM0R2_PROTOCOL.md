# SEM-0R2 — Interface-Qualified Replication Protocol

Status: **PRE-SCIENCE SUCCESSOR DESIGN**

Parent instrument: SEM-0R frozen manifest record SHA-256 `bdbb5f774ec36e444e9bd147cae770554330431aa68b444fb25650cbbcea2d96`.

Parent scientific execution: RUN-001 terminated at LIVE ordinal 2 with `prediction_3_invalid_label` and is classified `INTEGRITY_INVALID` under the frozen SEM-0R preregistration. RUN-001 is not retried, continued, rescored, or reinterpreted.

## Reason for successor

RUN-001 exposed an execution-interface failure before a semantic-control verdict could be produced. The parent runner requested JSON mode but did not constrain the `label` field to the registered enum at generation time, and it rejected malformed parsed output before persisting the exact raw model response. These are instrument-interface limitations, not evidence for or against semantic control.

SEM-0R2 is a new protocol event. It must never be described as continuation of RUN-001.

## Frozen semantic content

SEM-0R2 preserves without modification:

- the same 72 full-context cases;
- the same 16 replay cases;
- the same 16 context-ablation cases;
- the same registered gold;
- the same 36 controlled pairs;
- the same eight semantic families;
- the same thresholds and conjunctive verdict rule;
- the same transparent-baseline report;
- the same candidate model identity: `llama3.1:8b`;
- the same historical model blob SHA-256 `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`;
- the same Ollama runtime `0.21.2`;
- temperature 0 and the same deterministic seed basis.

Any semantic case, gold label, threshold, baseline, pair designation, or scorer change requires a differently named successor and cannot be folded into SEM-0R2.

## Interface repair

The only intended scientific-execution change is response serialization/control.

1. `/api/chat` receives a JSON Schema object in the Ollama `format` parameter rather than the string `"json"`.
2. The schema constrains `label` to exactly: `ASSERTED`, `ENTAILED`, `PRESUPPOSED`, `IMPLICATED`, `CONTRADICTED`, `UNKNOWN`.
3. The schema constrains top-level and prediction object keys and evidence item type.
4. Existing semantic payload validation still runs after generation. Schema-constrained generation does not replace validation.
5. No label aliases, spelling repair, case folding, fuzzy matching, or semantic normalization are permitted.
6. Every raw model response is persisted to an append-only raw-response log before JSON parsing or semantic payload validation.
7. A schema/validation failure still terminates the scientific run. There is no per-case retry.

## Interface qualification

Before a new scientific authorization can be created, the exact model/runtime must pass a non-benchmark interface qualification using synthetic serialization-only prompts that contain no SEM-0R cases, proposition texts, gold labels-as-targets, pair structure, or semantic-family information.

The qualification exists only to establish that the runtime accepts JSON-schema structured output and that raw-response persistence works. Qualification results cannot be scored as semantic evidence.

Failure of interface qualification blocks scientific authorization.

## Authorization

SEM-0R2 requires a new one-run authorization. The consumed RUN-001 authorization is never reused.

The new authorization must bind:

- parent frozen semantic-instrument manifest record hash;
- SEM-0R2 protocol/runner source hashes;
- exact model identity record;
- full/replay/ablation input hashes;
- baseline report hash;
- interface-qualification record hash.

Authorization is consumed before scientific request #1. A crash still spends it.

## Gold boundary

The parent order is unchanged:

`LIVE -> seal -> REPLAY -> seal -> CONTEXT_ABLATION -> seal -> open GOLD -> score once`

Raw-response logs are evidentiary execution artifacts and do not expose gold.

## Terminal outcomes

- `SEMANTIC_CONTROL_GATE_PASS`: every unchanged registered scientific gate passes.
- `SEMANTIC_CONTROL_GATE_FAIL`: one or more unchanged registered scientific gates fail after a complete valid execution.
- `INTEGRITY_INVALID`: execution cannot be validly scored because required bindings, seals, output structure, model identity, or execution constraints fail.

## Claim discipline

A SEM-0R2 result must disclose that RUN-001 was integrity-invalid and that SEM-0R2 added schema-constrained output and raw-response persistence after that failure. A successful SEM-0R2 result cannot be presented as though the interface repair had been part of RUN-001.

The repair is designed to reduce nuisance serialization failure, not to make the semantic task easier. Whether that claim holds is itself open to criticism and should be discussed in publication limitations.
