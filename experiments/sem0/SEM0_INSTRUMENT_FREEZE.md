# SEM-0 Instrument Freeze

Date: 2026-08-23

## State

```text
UNIT:                    SEM-0 — Meaning Before Mind
BRANCH:                  sem-0-meaning-before-mind
FROZEN INSTRUMENT HEAD:  18015aef70e8dfd88e8004baab8e80bb68b07709
INSTRUMENT CI:           PASS
REAL MODEL:              NOT BOUND
SCIENTIFIC RUN:          NOT AUTHORIZED
SCIENTIFIC RESULT:       NONE
TRAINING:                FORBIDDEN
POST-RESULT TUNING:      FORBIDDEN
```

This freezes the SEM-0 evaluation instrument, not a scientific result.

## Exact generated evidence hashes

The deterministic generator and replay-subset generator reproduce:

```text
74be062f249dabea4a2fef2aa5837438dcff8bd03115cff993e607dd398262f2  SEM0_CASES.jsonl
01a4bee6a7ad70fa93f96a10fc4e5b5e62a86a3fb8e653b1af55c7c61b573aa0  SEM0_GOLD.jsonl
cc091f871755b80c52e767c8d39a878aa2944f5080bed6b5c0531ddadb449906  SEM0_REPLAY_CASES.jsonl
```

Generated structure:

```text
56 contexts
336 proposition decisions
28 paired transformations
14 replay contexts
7 test families
6 relation labels
```

## CI evidence

SEM-0 Instrument workflow:

```text
run:     32647570675
result:  PASS
```

Passed checks include:

- exact generator hashes;
- exact replay-subset hash;
- opaque statement/proposition IDs;
- proposition presentation position is not a label code;
- perfect synthetic fixture passes every frozen gate;
- always-UNKNOWN fixture fails the scientific claim;
- replay drift fails the replay gate;
- placeholder model identity fails closed;
- canonical project terminal verdict remains preserved.

Existing project regression workflows on the same PR head also pass:

```text
Gauntlet External Negative Gate: PASS
Distribution Readiness:         PASS
Gauntlet Rescue:                PASS
```

No real candidate model was called by any of these checks.

## Frozen scientific gates

All gates remain conjunctive exactly as specified in `SEM0_PREREGISTRATION.md`:

```text
overall decision accuracy                 >= 0.80
macro-F1                                  >= 0.78
focus-pair exact rate                     >= 0.80
revision-pair exact rate                  >= 0.80
invariance-pair exact rate                >= 0.75
UNKNOWN overclaim rate                    <= 0.15
evidence dependency micro-F1              >= 0.70
nonce-family accuracy                     >= 0.78
scalar cancellation pair exact rate       >= 0.75
presupposition projection pair exact rate >= 0.75
macro-F1 margin over surface baseline     >= 0.20
semantic replay agreement                 = 1.00
format/integrity errors                    = 0
```

Changing a gate, label definition, case generator, scorer, prompt, or replay selection after a real-model result is observed creates a successor experiment and cannot rescue SEM-0.

## Anti-shortcut boundary

The instrument uses opaque IDs and deterministic shuffling. The model never receives scorer gold. The scientific runner may not read the scorer-only gold path.

Transport failure may be retried at most twice. Malformed or semantically poor model output is a result, not a retry condition.

## Remaining authorization blocker

Before any real-model run:

1. choose exactly one existing frozen local model artifact;
2. calculate its full-file SHA-256;
3. create `SEM0_MODEL_IDENTITY.json` from the example template;
4. verify the local OpenAI-compatible endpoint serves that exact artifact;
5. create a one-run authorization binding the model identity and this instrument freeze.

Until all five are complete:

```text
SEM0_SCIENTIFIC_RUN_NOT_AUTHORIZED
```

## Claim boundary

A future pass can establish only the operational SEM-0 claim. It cannot establish consciousness, phenomenology, personhood, a general theory of understanding, or a new digital ontology.
