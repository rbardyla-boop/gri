# TE0-E2 — Gate-Aware Interface Repair

Status: **PRE-EXECUTION / DEVELOPMENT PROTOCOL**

Parent engineering foundation: TE0 Forge exact qualified head `6203b3d55ef9e00e4a1941d0fdbf3999d7dc519e`.
Immediate predecessor: TE0-E1 exact head `2c9f924edaf31e5479b56cb556a8dd23ed8b9340`, terminal local development status `TE0_E1_INTERFACE_REPAIR_FAIL`.

## Why E2 exists

TE0-E1 correctly refused promotion. Its selected DEV champion optimized exact score plus simplicity before later gates were evaluated. The winner then failed contract structural validity, registered attacks, raw-improvement, and component-credit gates. E1 also exposed recoverable alternate JSON shapes that were not covered by its pure interface transforms.

E2 is a separately disclosed successor. It does **not** rerun, repair, rescore, or reinterpret E1.

## Question

> On fresh BUILD/DEV pools, can a bounded ToolSmith plus a gate-aware Composer discover a deterministic repair chain that preserves explicitly present information, survives fixed interface attacks, and satisfies all development gates before any hidden Vault exists?

This is engineering/interface research only. It is not semantic-science evidence.

## Frozen producer

Same historical producer identity as E1:

- model: `llama3.1:8b`
- FROM-blob SHA-256: `667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29`
- Ollama: `0.21.2`
- temperature: `0`
- deterministic per-case seed
- one request attempt per case
- no model-weight changes

Identity mismatch stops E2.

## Fresh development pools

E2 uses new public deterministic seeds:

- BUILD seed text: `TE0-E2-PUBLIC-BUILD-v1`
- DEV seed text: `TE0-E2-PUBLIC-DEV-v1`
- BUILD count: 24
- DEV count: 24

No E1 DEV row is reused as an E2 scoring row.

No Vault seed, Vault case, Vault authorization, or Judge execution is created during E2 development.

## Allowed repair information

The producer sees the synthetic prompt. Repair tools see only the sealed raw producer text.

Repair tools may transform only information already present in that text. They may not read the prompt, target, case metadata, network, filesystem, or hidden state.

## E2 ToolSmith extension

E2 retains E1's pure operations and adds one allow-listed operation:

`canonicalize_label_evidence_schema`

It may recognize only these recoverable forms:

1. direct object containing `label` and `evidence`;
2. exactly one top-level key whose case-insensitive value is one allowed label, with an object value containing one of `evidence`, `evidenceArray`, or `evidenceMultiset`.

It emits exactly `{label, evidence}` using only values present in the input. Ambiguity, missing fields, unknown labels, non-list evidence, or conflicting candidate evidence fields fail closed. It does not fuzzy-match or invent content.

Label whitespace/case normalization and evidence set canonicalization remain separate operations so mechanism credit can be tested by ablation.

## Fixed registered attacks

Before execution E2 registers:

1. canonical preservation;
2. prose wrapper around an otherwise valid JSON object;
3. label case/whitespace plus evidence duplicate/reordering noise;
4. nested-label schema representation using an allowed label key and explicit evidence field.

These attacks are public development stressors, not hidden tests.

## Gate-aware selection

For every typed candidate chain within the bounded search budget, E2 computes on DEV:

- exact-target rate;
- contract structural-validity rate;
- preservation rate on already-valid raw cases;
- full fixed attack-set exact rate;
- improvement over raw exact rate;
- margin over transparent nulls;
- chain depth and cost.

Selection is lexicographic and fixed before model collection:

1. number of development gates passed;
2. minimum of DEV exact, structural validity, preservation, and attack-set exact;
3. DEV exact rate;
4. attack-set exact rate;
5. structural-validity rate;
6. preservation rate;
7. improvement over raw;
8. null margin;
9. lower tool count;
10. lower cost;
11. deterministic tool-name ordering.

This replaces E1's exact-score-first champion selection. It does not lower any gate.

## Development gates

A champion freezes only if all are true:

- DEV exact >= `0.95`;
- contract structural validity >= `0.98`;
- raw exact improvement >= `0.10`, unless raw exact >= `0.98`;
- margin over strongest transparent null >= `0.20`;
- preservation of already-valid outputs = `1.00`;
- fixed attack-set exact = `1.00`;
- Grinder unresolved failures = `0`;
- every retained component earns positive mechanism credit under attack-set ablation.

If raw exact >= `0.98`, terminal status is `TE0_E2_REPAIR_NOT_NEEDED`.
If no candidate satisfies every gate, terminal status is `TE0_E2_INTERFACE_REPAIR_FAIL`.
If all gates pass, terminal development status is `TE0_E2_DEVELOPMENT_CHAMPION_FROZEN`.

## Stop rule

E2 development is one frozen BUILD/DEV execution on the exact source head. A failing E2 result is preserved; E2 is not repeatedly modified and rerun against the same observed DEV bytes.

Only an E2 development champion may justify designing a later one-shot Vault authorization/Judge stage. A Vault is not part of this pre-execution branch state.
