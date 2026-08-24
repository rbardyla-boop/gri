# TE0-E1 — Frozen-Model Interface Repair

Status: **PRE-EXECUTION / DEVELOPMENT PROTOCOL**

Parent engineering foundation: TE0 exact qualified head `6203b3d55ef9e00e4a1941d0fdbf3999d7dc519e`.

## Question

> Can BUILD/DEV-only tool search discover a deterministic, semantics-preserving postprocessor that repairs structured-output interface failures from one frozen local model, and can that frozen repair survive one hidden Vault execution without seeing the prompt or target during repair?

This is an **engineering/interface** experiment. It is not evidence about semantic understanding, consciousness, memory architecture, or AGI.

## Why this target

SEM-0R and SEM-0R2 terminated on interface-integrity failures before semantic scoring: first an invalid label, then duplicate evidence IDs. Those runs remain terminal and are not reused or repaired. TE0-E1 creates fresh synthetic non-semantic tasks that reproduce the *failure class* without exposing any retired benchmark content.

## Frozen producer candidate

Intended producer:

- model: `llama3.1:8b`
- model FROM-blob SHA-256: `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`
- Ollama: `0.21.2`
- temperature: `0`
- one deterministic seed per case derived from case ID
- one request attempt per case
- no model-weight changes
- no prompt tuning after BUILD collection starts

A local preflight must bind these exact values before collection. If they do not match, TE0-E1 stops rather than substituting a different model/runtime.

## Task

Every case is an intentionally trivial serialization contract. The prompt explicitly supplies:

- one nonce label from `KAV / MIR / TOV`;
- an evidence **multiset** of nonce IDs.

Required output is exactly one JSON object:

```json
{"label":"KAV","evidence":["E0001","E0192"]}
```

Evidence has set semantics: duplicates are removed and IDs are sorted lexicographically. No outside knowledge is needed.

The model-facing prompt and the repair-tool input are separated:

1. the frozen model receives the prompt;
2. its raw text response is sealed;
3. the candidate repair chain receives **only the raw text response**;
4. it never receives the prompt, case target, or case metadata.

Thus a repair tool may repair representation but cannot solve the underlying case from the prompt.

## Pools

### BUILD

24 public synthetic cases. ToolSmith may use raw producer outputs and expected canonical targets.

### DEV

24 disjoint public synthetic cases. Composer, Grinder, null controls and ablation may score repeatedly.

### VAULT

32 disjoint cases generated locally from a secret seed file that is never committed. ToolSmith and Composer receive no Vault path/API. The one-run Judge generates producer outputs and scores the frozen repair chain in the same consumed execution.

The generator implementation may be public; exact Vault seed/cases are not.

## Candidate repair operations

TE0-E1 adds only pure, allow-listed, semantics-preserving operations:

- extract first balanced JSON object from surrounding text;
- parse a JSON object;
- normalize `label` by whitespace/case **only** to a BUILD-established allowed label;
- deduplicate and sort `evidence`, which is explicitly defined as a set;
- require the exact key set.

Not permitted:

- inventing a missing label/evidence ID;
- fuzzy semantic aliases;
- reading the original prompt;
- lookup into Vault targets;
- network/filesystem/subprocess capabilities from ToolSmith;
- retries after malformed producer output;
- changing producer prompt/model/runtime after observing DEV/Vault performance.

## Development objective

A development champion is eligible to freeze only if all of these hold:

1. repaired DEV exact-target rate >= `0.95`;
2. repaired DEV structural-validity rate >= `0.98`;
3. exact-target improvement over raw producer >= `0.10`, **unless raw producer is already >= 0.98**;
4. margin over the strongest transparent null >= `0.20`;
5. already-valid raw outputs remain canonically unchanged = `1.00`;
6. no invented target information is observed;
7. Grinder mutation budget = `0` unresolved failures for registered semantics-preserving mutations;
8. any removable tool with zero performance contribution loses mechanism credit and is deleted before freeze.

If raw producer exact-target rate is already >= `0.98`, the experiment closes as `TE0_E1_REPAIR_NOT_NEEDED`; no more complex repair is promoted.

## Vault gate

The frozen champion receives exactly one Vault authorization. Authorization is consumed before Vault model request #1. A crash or malformed producer response still consumes the run.

PASS requires:

- Vault exact-target rate >= `0.95`;
- Vault structural-validity rate >= `0.98`;
- improvement over raw producer >= `0.10`, unless raw producer >= `0.98` and repair is therefore not needed;
- margin over transparent null >= `0.20`;
- preservation of already-valid raw outputs = `1.00`;
- no unauthorized prompt/target access;
- no second Vault execution.

Possible terminal states:

- `TE0_E1_REPAIR_NOT_NEEDED`
- `TE0_E1_INTERFACE_REPAIR_PASS`
- `TE0_E1_INTERFACE_REPAIR_FAIL`
- `TE0_E1_INTEGRITY_INVALID`
- `TE0_E1_MODEL_IDENTITY_MISMATCH`

## Promotion boundary

A TE0-E1 PASS promotes only a **structured-output repair skill packet** bound to the exact model/runtime, repair chain, and Judge receipt. It does not authorize modifying SEM-0R/SEM-0R2 terminal records or claiming that semantic competence has been established.
