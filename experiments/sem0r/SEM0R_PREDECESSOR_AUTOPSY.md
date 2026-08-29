# SEM-0R Predecessor Autopsy

Date: 2026-08-23

## State

```text
PREDECESSOR:              SEM-0 first instrument
REAL MODEL EXECUTIONS:    0
SCIENTIFIC RESULTS:       0
TRAINING RUNS:            0
PREDECESSOR VERDICT:      RETIRED BEFORE SCIENCE
SUCCESSOR:                SEM-0R
```

The first SEM-0 instrument was frozen and mechanically valid as software, but a hostile pre-run review found that it was not a sufficiently strong scientific instrument for the intended claim.

The failure was discovered before any candidate model saw the benchmark.

## Defects found

1. Every case contained exactly six propositions with exactly one instance of each relation label. Shuffling hid position, but the one-of-each label multiset remained a global shortcut.
2. The registered comparison baseline was only exact-text matching versus `UNKNOWN`, which was too weak for repeated linguistic templates.
3. Seven semantic schemas were repeated with nonce substitutions, leaving substantial template-recognition opportunity.

No scientific result was produced, so no result was rescued, reinterpreted, or tuned away.

## Successor requirements

SEM-0R was authorized as a new instrument only if it:

- varies proposition count and relation multiplicity per case;
- removes the one-of-each constraint;
- uses multiple renderers per semantic family;
- contains both meaning-changing revision pairs and meaning-preserving invariance pairs;
- registers stronger transparent shortcut baselines;
- uses a context-ablation probe;
- withholds credit unless the candidate exceeds the strongest registered transparent shortcut;
- preserves exact dependency/evidence scoring, `UNKNOWN` restraint, and replay;
- remains frozen before any real-model call.

## Allowed claim

> Pre-science adversarial review invalidated the first SEM-0 instrument for the intended claim, and it was retired before any real-model result was observed.

This is an instrument-validation result, not evidence for or against machine understanding.
