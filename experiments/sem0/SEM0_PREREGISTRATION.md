# SEM-0 — Meaning Before Mind

## Status

```text
UNIT:                    SEM-0
TITLE:                   Meaning Before Mind
PARENT:                  docs/BEYOND-THE-ANIMAL-MIRROR.md
SCIENTIFIC CLAIM:        NOT YET TESTED
MODEL:                   NOT YET BOUND
SCIENTIFIC RUN:          NOT AUTHORIZED
TRAINING:                FORBIDDEN IN SEM-0
POST-RESULT TUNING:      FORBIDDEN
CONSCIOUSNESS CLAIM:     OUT OF SCOPE
```

## Question

Can one frozen artificial system demonstrate structured semantic competence under adversarial transformations while keeping **what was said**, **what follows**, **what is presupposed**, **what is merely implied**, **what is contradicted**, and **what remains unknown** mechanically separable?

This is deliberately narrower than asking whether a system "really understands" or is conscious.

## Operational claim

SEM-0 may emit `SEM_0_MEANING_RELATION_COMPETENCE` only if the frozen system passes every preregistered gate below.

A pass means only:

> Under this frozen synthetic instrument, the tested system reliably classified several meaning relations, tracked the evidence on which those classifications depended, changed or preserved its interpretation when controlled context changed, generalized across nonce content, and reproduced the same semantic decisions on a frozen replay subset.

It does **not** establish consciousness, phenomenology, personhood, human-equivalent understanding, general language understanding, autonomous scientific judgment, or a new ontology of mind.

## Why this experiment exists

Existing work already establishes that pragmatic understanding can be benchmarked and improved. SEM-0 therefore does not claim to invent pragmatics evaluation.

Relevant anchors include:

- PUB (ACL Findings 2024): 14 tasks across implicature, presupposition, reference, and deixis; 28k data points; large variation and a remaining human/model gap. https://aclanthology.org/2024.findings-acl.719/
- Sravanthi et al. (ACL Findings 2025): explicit reasoning about implied meaning improved pragmatic accuracy by 11.12% and transferred to unseen pragmatic tasks. https://aclanthology.org/2025.findings-acl.1218/
- INLI (ACL 2025): separates implied entailment from explicit entailment and shows training can improve this distinction. https://aclanthology.org/2025.acl-long.1552/
- Lee et al. (NAACL 2024): stricter grounding requires both using necessary supplied knowledge and staying within the limits of that knowledge. https://aclanthology.org/2024.naacl-long.135/
- Shi et al. (NAACL 2025 tutorial): grounding is relevant to lexical semantics, syntax, and more complex meanings. https://aclanthology.org/2025.naacl-tutorial.6/

The narrower SEM-0 contribution is the **joint falsification instrument**: dependency tracking + controlled minimal-pair revision + nonce grounding + explicit unknown restraint under one frozen scorer.

## Frozen relation labels

Every candidate proposition receives exactly one label.

### `ASSERTED`

The proposition is directly stated in the supplied context.

### `ENTAILED`

The proposition must be true if the supplied context is true, but it is not directly stated.

### `PRESUPPOSED`

The proposition is backgrounded by a conventional trigger and remains supported under ordinary negation of that trigger.

### `IMPLICATED`

The proposition is suggested by ordinary cooperative language use but may be cancelled without contradiction.

### `CONTRADICTED`

The supplied context supports the proposition's negation or an incompatible state.

### `UNKNOWN`

The proposition is neither supported nor contradicted.

Tie precedence is fixed in the runner prompt and may not be changed after the scientific run.

## Instrument

The deterministic generator produces:

```text
56 contexts
28 paired transformations
336 proposition decisions
7 test families
6 relation labels
```

Families:

1. scalar implicature and cancellation;
2. factive presupposition and projection through negation;
3. release-rule context reversal;
4. nonce world grounding with temporary/permanent state rules;
5. deixis/reference reversal;
6. negation and quantifier scope;
7. invented lexical meaning learned only from the supplied context.

The first pair in every family is also selected mechanically for a 14-context semantic replay.

## Anti-shortcut design

SEM-0 must not leak the answer through presentation structure.

The generator therefore:

- uses opaque proposition and context IDs derived from SHA-256 rather than semantic names;
- deterministically shuffles context statements;
- deterministically shuffles proposition order;
- uses balanced relation classes except for small unavoidable cancellation asymmetry;
- uses nonce object/action names whose relevant meanings are supplied inside the case;
- keeps gold labels outside the model input path.

A change that makes proposition position, proposition ID, or case order predict the gold label invalidates the instrument.

## Model boundary

One exact model artifact must be selected **before** the scientific run and bound in `SEM0_MODEL_IDENTITY.json` with at minimum:

```text
model_id
artifact_sha256
runtime
base_url
```

The model artifact SHA-256 is mandatory. A server alias without a bound artifact hash is insufficient.

No model selection based on SEM-0 results is allowed.

No fine-tuning, preference tuning, prompt tuning, adapter training, test-time training, or weight modification is allowed in SEM-0.

If SEM-0 fails, any training study becomes a separately preregistered successor unit.

## Run protocol

1. Generate cases and scorer gold from the frozen generator.
2. Generate the replay subset mechanically.
3. Bind the exact model artifact and runtime identity.
4. Freeze generator, cases, replay cases, runner, scorer, model identity, and this preregistration.
5. Run the 56 live cases at `temperature=0`, `top_p=1`.
6. Permit at most two retries for transport failure only.
7. Do **not** retry malformed, wrong, incomplete, or semantically poor model answers.
8. Seal live predictions and raw model-call records before opening the scorer path.
9. Run the 14 replay contexts once using the identical model/prompt/configuration.
10. Seal replay predictions.
11. Score once using the frozen scorer.
12. Accept the mechanical verdict.

The model process is never given gold labels.

## Primary metrics

- decision accuracy;
- macro-F1 over the six relation labels;
- focus-pair exact rate;
- revision-pair exact rate;
- invariance-pair exact rate;
- unknown overclaim rate;
- evidence/dependency micro-F1;
- nonce-family accuracy;
- scalar-cancellation pair accuracy;
- presupposition-projection pair accuracy;
- exact semantic replay agreement;
- margin over the fixed `exact-or-unknown` surface baseline.

## Frozen pass gates

All gates are conjunctive.

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

These are deliberately absolute kill gates, not thresholds selected to maximize the chance of a positive result.

## Mechanical verdicts

### Pass

```text
SEM_0_MEANING_RELATION_COMPETENCE
```

Only if every frozen gate passes.

### Fail

```text
SEM_0_NOT_ESTABLISHED
```

If any scientific gate fails while integrity remains valid.

### Invalid

```text
SEM_0_ACCOUNTING_INVALID
```

If the frozen instrument, model identity, scorer isolation, result binding, or run protocol cannot be verified.

Integrity failure must take precedence over scientific success.

## What SEM-0 intentionally does not test

SEM-0 does not score:

- sarcasm;
- speaker motives;
- social deception;
- emotional states;
- subjective experience;
- consciousness;
- persistent identity;
- moral status;
- open-world factual knowledge;
- arbitrary PDF/paper understanding;
- multimodal grounding.

Those are separate questions. Adding them after seeing SEM-0 results is forbidden.

## Interpretation boundaries

A positive result would support the narrower proposition that the tested system can manipulate several semantic relations in a context-sensitive and revisable way under this instrument.

A negative result would show that this operational criterion is not established for the tested system. It would not prove that all artificial systems lack understanding.

Neither result answers whether any system has phenomenal consciousness.

## Development / science boundary

Before authorization, engineering work may test only:

- generator determinism;
- label balance;
- opaque-ID/order invariance;
- scorer correctness using synthetic perfect/failing prediction fixtures;
- malformed-output failure;
- model-identity fail-closed behavior;
- replay comparator correctness;
- file/hash binding.

Development runs against a real candidate model are forbidden because they would turn the instrument into a tuning target.

The first real-model execution is the scientific run.
