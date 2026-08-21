# DMC-04R — Repair Required

Terminal state: `DMC_04R_REPAIR_REQUIRED`

The frozen preflight and the seed-9090 deterministic replay passed. Evidence
seed 1337 completed its 80-epoch retriever training and its checkpoint was
written. During the preregistered A-only control evaluation, the frozen
temporal resolver raised `ValueError: selected descriptor group has no
temporally eligible record` for a history case.

This is a runner execution defect, not a retrieval result. The control should
record an ineligible selected group as a retrieval miss. Because the first
evidence seed was already consumed, the run was not retried and seeds 1338–1341
were not executed.

No learned metrics, advancement gates, or scientific retrieval claim are
valid from this partial run. The seed-1337 checkpoint is preserved for audit;
it must not be silently reused as a replacement evidence run.
