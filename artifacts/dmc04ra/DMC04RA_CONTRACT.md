# DMC-04R-A — Fixed Missing-Retrieval Evaluation Semantics

Status: **AMENDMENT PREREGISTERED; FRESH DMC-04R2 EXECUTION AUTHORIZED**

This additive amendment preserves historical `DMC_04R_REPAIR_REQUIRED` and
changes only the evaluator treatment of one frozen resolver condition.

Old behavior:

```text
selected descriptor group
→ no temporally eligible record
→ raise ValueError
→ abort experiment
```

New behavior:

```text
selected descriptor group
→ no temporally eligible record
→ retrieval_hit = 0
→ predicted answer = null
→ answer_hit = 0
→ continue evaluation
```

Only the exact `selected descriptor group has no temporally eligible record`
`ValueError` is converted. Other exceptions still abort.

The fresh execution is named DMC-04R2. It reuses evidence seeds 1337–1341
under corrected evaluator semantics. Seed 1337 was consumed by the invalid
DMC-04R execution and is explicitly recorded as a fresh corrected execution,
not an unnoticed retry. No model, data, optimizer, threshold, decoder, or
training protocol changes.
