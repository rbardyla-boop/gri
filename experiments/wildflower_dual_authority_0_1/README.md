# WILDFLOWER Dual-Authority-0.1

This is a local-only successor to the frozen Dual-Authority-0 experiment.
Seed 310 and its result remain historical evidence and are not modified here.

The successor separates two previously conflated outcomes:

1. `alternate_support_preservation`: an existing derived support remains
   committed after one parent support path is retired and world-rooted parent
   claim keys remain valid.
2. `recomputed_after_parent_change`: the old parent claim keys are invalidated,
   old provenance becomes ineffective, and grounded recomputation reconstructs
   the same or a changed derived value from corrected parents.

The implementation is intentionally locked at the micro-simulation/pre-lock
stage. Development seeds are 311--313. Qualification seeds 314--315 remain
untouched until the pre-lock report is reviewed.

Run the local checks with:

```bash
PYTHONHASHSEED=0 python -m compileall -q experiments/wildflower_dual_authority_0_1
ruff check experiments/wildflower_dual_authority_0_1
PYTHONHASHSEED=0 python -m pytest -q -W error experiments/wildflower_dual_authority_0_1/tests
```
