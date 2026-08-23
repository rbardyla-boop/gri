# SEM-0 Pre-Science Instrument Autopsy

Date: 2026-08-23

## Mechanical state

```text
UNIT:                    SEM-0 — Meaning Before Mind
ORIGINAL INSTRUMENT:     FROZEN
REAL MODEL RUNS:         0
SCIENTIFIC RESULTS:      0
TRAINING:                0
STATUS:                  RETIRED BEFORE SCIENCE
REASON:                  STRUCTURAL SHORTCUT / WEAK NULL DISCOVERED
SUCCESSOR:               REQUIRED
```

This record does not change any scientific result because no scientific model execution occurred.

## Why the frozen instrument is being retired

A hostile pre-run audit found that the first SEM-0 instrument is not strong enough for the operational claim we want to test.

### 1. One-of-each relation leakage

Every generated case contains exactly six propositions and exactly one instance of each frozen relation label:

```text
ASSERTED
ENTAILED
PRESUPPOSED
IMPLICATED
CONTRADICTED
UNKNOWN
```

The proposition order is shuffled, so position itself does not encode the answer. However, the per-case label multiset is still fixed. A system that identifies only some easy relation cues can use the hidden one-of-each constraint to infer remaining labels. That is a structural shortcut not required by the intended semantic task.

### 2. Registered null is too weak

The scorer compares the candidate primarily against an `exact-or-unknown` surface baseline:

```text
exact proposition text appears in context -> ASSERTED
otherwise                              -> UNKNOWN
```

That is a useful floor but not a strong null for a benchmark built from repeated semantic templates. A transparent lexical/structural heuristic can exploit triggers such as `some`, `did not stop`, `realized that`, `if and only if`, `here means`, and repeated rule forms without implementing the broader semantic-control behaviour the project wants to measure.

### 3. Template repetition is too strong

The instrument repeats seven English schemas four times each with nonce substitutions. Nonce names prevent simple memorization of entities, but the semantic form remains highly regular. A positive result would therefore mix semantic competence with template recognition.

### 4. The current interpretation would be too easy to overstate

The frozen preregistration already narrows the claim, but the central project question is stronger than success on a small fixed family of templates. Running a real model now would consume the first scientific observation on an instrument whose shortcut surface is already known.

## Decision

Do not run the original frozen SEM-0 instrument.

Do not tune a model against it.

Do not change the frozen generator or scorer in place and reuse the original freeze claim.

Instead create a successor instrument with a new freeze and explicit lineage from this autopsy.

## Successor requirements

The successor must, before any real-model call:

1. vary the number and multiplicity of relation labels per case so the label multiset is not inferable;
2. use multiple surface realizations for the same semantic relation;
3. include paired meaning-preserving paraphrases and meaning-changing minimal perturbations;
4. register stronger transparent baselines, including a lexical-trigger baseline and a constraint-aware structural baseline;
5. withhold scientific credit if a transparent baseline satisfies the same absolute gates;
6. preserve nonce-world and revision tests while distinguishing text-defined synthetic grounding from physical/world grounding;
7. keep exact evidence/dependency scoring;
8. preserve UNKNOWN restraint and deterministic replay;
9. maintain the consciousness/phenomenology firewall;
10. remain frozen before the first real-model execution.

## Allowed claim from this autopsy

Only:

> Pre-science adversarial review found a structural shortcut and weak-null problem in the first SEM-0 instrument, so it was retired before any real-model result was observed.

This is instrument validation, not a result about artificial understanding.