# SRI-1A-α.4.1 Independent Audit

## Verdict

`SRI_ALPHA4_1_REPAIR_REQUIRED`

Recruitment remains `SRI_ALPHA4_RECRUITMENT_NOT_AUTHORIZED`.

Uploaded toolchain SHA-256:

`2f5880fd14ef5333d541839e6bd8eff73de8e0bbecafe19ec5f9f488caef0190`

Frozen α.4 parent package SHA-256 independently verified:

`40f281e3705d5dc35c1e2ded3c3cf31a12a656bda66e1982eafd0f196cfd291d`

## Reproduction findings

1. The uploaded toolchain does not reproduce its stated `3 passed` result standalone. Independent unpack + `pytest -q` returns `1 failed, 2 passed` because `test_untouched_package_is_not_authorized` assumes the α.4 parent zip is adjacent to the unpacked toolchain.

2. More importantly, the production validator can be made to authorize a completely fabricated self-consistent configuration. A temporary root was populated with arbitrary fake files. `operational_config.json` supplied both each fake file path and the matching SHA-256, set `authority=AUTHORITATIVE`, `zero_human_replay=true`, `scientific_invariants_unchanged=true`, and a syntactically accepted ethics disposition. The validator returned exit code `0` and printed `SRI_ALPHA4_RECRUITMENT_AUTHORIZED`.

3. No production authorization receipt was created after that exit-0 result.

## Root causes

- Expected artifact hashes and artifact paths are both supplied by the same untrusted `operational_config.json`; there is no independent trust anchor.
- The validator does not verify the required frozen α.4 parent package SHA-256 before extraction/validation.
- The validator does not bind the α.4 freeze SHA, manifest SHA, or manifest entries to immutable trusted constants.
- `scientific_invariants_unchanged` is accepted as a boolean assertion rather than recomputed from an invariant manifest and authoritative parent hashes.
- `zero_human_replay` is accepted as a boolean assertion rather than executing/verifying the frozen ingestion replay.
- Ethics evidence is hash-checked only as an arbitrary file; its disposition-specific evidence is not validated.
- There is no deterministic consent renderer.
- There is no executable zero-human ingestion replay implementation.
- There is no scientific-invariant manifest generator/verifier.
- There is no authorization receipt writer on production success.
- All failures collapse to exit code 2; required integrity/invariant/ingestion/ethics exit classes are absent.
- Only three tests exist; the required adversarial matrix is not implemented as tests.

## Required repair

Create `SRI-1A-α.4.1R — TRUST-ANCHOR & EXECUTABLE-GATE REPAIR`.

The repaired toolchain must derive trust from a frozen toolchain trust-anchor file/package whose SHA is externally fixed, not from expected hashes supplied by the operational config. It must independently execute invariant verification and zero-human ingestion replay, validate ethics evidence structure, write a production authorization receipt only on genuine success, and implement the full adversarial test matrix.

No scientific α.2/α.2.1/α.3 artifact may be changed.
