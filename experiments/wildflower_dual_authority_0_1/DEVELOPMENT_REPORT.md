# Dual-Authority-0.1 development report

Status: stopped before qualification. No qualification seed was executed and no
qualification freeze was created.

## Local boundary

- Branch: `wildflower-local-lab`
- Historical checkpoint: `77d25c6a60ad1556d20ab5fbd82897f7b0e50fee`
- Push hook: installed and executable at `.git/hooks/pre-push`
- Seed-310 frozen source and recovered scored result: unchanged
- GitHub activity: none

## Verification gates

The successor package passes the local checks after the interrupted run:

```text
PYTHONHASHSEED=0 python -m compileall -q experiments/wildflower_dual_authority_0_1  PASS
ruff check experiments/wildflower_dual_authority_0_1                       PASS
PYTHONHASHSEED=0 python -m pytest -q -W error experiments/wildflower_dual_authority_0_1/tests  30 passed
```

The deterministic micro-suite covers alternate support, shared parents,
recomputation, cascading descendants, diamonds, cycle rejection, duplicate
insertion, witness ordering, bounded storage, and semantic replay.

## Development seed execution

The exact requested command was started for model seed 311:

```text
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m experiments.wildflower_dual_authority_0_1.run_dual_authority01 --seed 311
```

It remained CPU-bound for approximately one hour without reaching the JSON
write boundary. During the final observation it used one saturated CPU core and
approximately 640--646 MiB RSS, with no evidence of memory runaway. No partial
scientific result was accepted. The process was terminated cleanly at the
bounded interval.

Seeds 312 and 313 were not started because seed 311 did not produce a valid
artifact. Seeds 314 and 315 were not started, as required. There are no files
under this package's `artifacts/` directory.

## Scaling diagnosis

This is an operational failure of the current development scorer, not a
scientific PASS or FAIL for Dual Authority. The successor store refreshes all
claim statuses after every support insertion and again during support
revocation. Each refresh recursively evaluates effective and grounded support
paths; revocation also computes before/after effective maps. As the active
support graph grows, those repeated whole-store traversals dominate the run.

The observed result is therefore:

```text
development evidence: INCOMPLETE
scientific gates: NOT MEASURED
qualification: NOT AUTHORIZED
```

The next permitted action is to redesign or instrument the refresh/index path
locally, then rerun only the development seeds 311, 312, and 313. Do not tune
or rerun seed 310, and do not execute 314 or 315 until a new qualification
freeze is explicitly created from adequate development evidence.

