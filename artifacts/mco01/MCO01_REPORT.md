# MCO-01 — STORE ALL, THINK SMALL

## Claim under test

A complete cheap external event history can answer delayed 2–5-hop dependency questions while exposing no more than 16 records to the active reasoner. The discriminating comparison is whether one-shot retrieval is sufficient or iterative `NEED(...)` acquisition adds material capability.

## Check

Self-verified deterministic synthetic benchmark: 20 histories, 160 queries, 555,500 event records, four history sizes, five evidence seeds, and two byte-identical valid scientific runs after excluding declared wall-clock fields. Required records were position-randomized, and no critical path fit within any contiguous 16-record window.

| System | Answer | Critical recall | Provenance | Max active | Records retrieved | Rounds | External reads | Mean wall seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full_history_oracle | 100.00% | 100.00% | 100.00% | 100000 | 27775.00 | 0.00 | 27775.00 | 0.004595 |
| recent_16 | 0.00% | 4.67% | 0.00% | 16 | 16.00 | 0.00 | 16.00 | 0.000906 |
| exact_structured_lookup | 100.00% | 100.00% | 100.00% | 5 | 3.50 | 1.00 | 4.50 | 0.000023 |
| conventional_one_shot_retrieval | 5.00% | 37.32% | 5.00% | 16 | 16.00 | 1.00 | 27775.00 | 0.140908 |
| iterative_need_retrieval | 100.00% | 100.00% | 100.00% | 6 | 4.50 | 3.50 | 4.50 | 0.000033 |

## Verdict — PASS

`MCO_01_ITERATIVE_ACQUISITION_ADVANCES`

Iterative minus one-shot answer accuracy was 95.00% overall and 100.00% on 3–5-hop cases. Exact structured lookup and iterative acquisition both remained within the 16-record active cap if their recorded gates show `pass: true`.

## Criteria

- Frozen identity and dataset integrity: **PASS**
- Exact population and nonzero denominators: **PASS**
- Byte-identical replay after runtime exclusion: **PASS**
- Full-history oracle at every load: **PASS**
- Exact structured bounded-quality gate: **PASS**
- One-shot bounded-quality gate: **FAIL**
- Iterative bounded-quality gate: **PASS**

## Assumption register

- Events are already structured into subject, relation, object, source, update, and provenance fields.
- Source priority is correct and shared equally by all store-all systems.
- External indexes are exact, lossless, and cheap enough to retain the full synthetic history.
- The active-record count measures reasoner-visible records; persistent index state and external planner operations are reported separately.
- Wall-clock values are descriptive local measurements and are excluded from verdict and replay identity.

## Credit assignment

Credit is limited to complete structured storage plus transparent indexing and bounded acquisition. Iterative retrieval receives credit only for the measured gap over the equally informed one-shot system. DMC, learned retention, model inference, tokenizer savings, and production economics receive no credit from MCO-01.

## Verification gap

No independent verifier was available, so this is explicitly self-verified. The test does not establish robustness to natural language, extraction errors, approximate indexes, adversarial source metadata, concurrent writes, or real model reasoning. Exact structured lookup is a strong transparent planner baseline, not a claim that arbitrary real queries can be compiled perfectly.

## Stop/continue decision

STOP MCO-01 at this terminal deterministic verdict. The bounded-history gate passed; a separately frozen language/tokenizer/model-cost experiment is now eligible, but was not run here.

## Maturity status

`DETERMINISTIC_SYNTHETIC_MECHANISM_EVIDENCE`
