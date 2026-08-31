# WILDFLOWER Dual-Authority-0.2 run history

## 320-R1

- Status: `OPERATIONAL_FAILURE`
- Exit: `1`
- Cause: runner stable-reference / `ClaimKey` mismatch
- Failed lookup: `recomputed_by_reference[transition.claim]`
- Scientific artifact: none
- Scientific gates: not assessed
- Scientific verdict: `INCONCLUSIVE`
- Run log SHA-256: `87b28b92c42222346b579f7568ddd671474ef55161a119481951fe9f51cbdd43`

The map was keyed by `stable_reference: int`, while `transition.claim` was a
`ClaimKey` tuple `(stable_reference, value)`. The failure occurred while
wiring recomputation targets, before a scientific result could be published.

The 320-R1 repair changes only the lookup to use `transition.claim[0]`, adds
focused type annotations and regression coverage, and does not change the
predictive mechanism, selectors, thresholds, metrics, provenance semantics,
or controls. Seed 320 has still produced no scientific evidence.

## 320-R2

- Status: `OPERATIONAL_FAILURE`
- Exit: `124`
- Cause: 30-minute operational watchdog timeout
- Scientific artifact: none
- Scientific gates: not assessed
- Scientific verdict: `INCONCLUSIVE`
- Run log: `/tmp/wildflower_dual_authority02_seed320_R2_run.log`
- Run log SHA-256: `ca19f15cb83048ec19fd12fa9dad49d374bece97d12c0ac3df24f34ff3262926`
- Watchdog wall limit: `1800` seconds

The process remained CPU-bound until the watchdog terminated it. The wrapped
`/usr/bin/time -v` process was terminated with the runner, so final user/system
CPU and time-reported RSS were not emitted. Read-only process monitoring
observed approximately 99.9% CPU and a peak RSS of 716,532 kB before timeout.
No partial scientific artifact was published. No retry was performed.
