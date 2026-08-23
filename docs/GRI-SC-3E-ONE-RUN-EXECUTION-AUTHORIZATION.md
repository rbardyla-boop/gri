# GRI-SC-3E — One-Run Execution Authorization

**Status:** `ONE_EXECUTION_AUTHORIZED_BEFORE_RUN`

This unit binds the frozen SC-3 contract to exactly one possible scientific
execution. It does not start that execution.

```text
EXECUTIONS AUTHORIZED: 1
DEVELOPMENT RUNS:       0
RETRIES:                0
POST-RESULT TUNING:     FORBIDDEN
SCIENTIFIC RESULT:      NONE
```

## Immutable authorization anchors

```text
SC-3 machine contract:
590d6606ff23cdfb02e9285f71772c9fab52d5b46fdd693a842ad83b5a242987

SC-3 record:
5606d312b5148debb9e1cac223bd00bbd1bd530c2ed08901b0d037dac36bdeb2

SC-3 verification:
d5cff851674232b3829ee0f7083655c07d11d7c749779c811c5398bf30fb74f4

SC-2 freeze:
03ec6bc36c8b5d4d764bdbef3bccf875294c1b9b8512d23614643beef0638e9d
```

The machine-readable SC-3 contract hash is the operative contract anchor.

## One command path

The authorized execution path is exactly:

```text
preflight
→ immutable environment receipt
→ one frozen scientific execution
→ controls + causal ablations
→ full restart verification
→ deterministic replay
→ mechanical verdict
```

The reserved entrypoint is:

```bash
python3 experiments/run_gri_sc3.py \
  --authorization experiments/candidates/GRI-SC-3E-one-run-execution-authorization.json
```

The entrypoint must refuse execution when any frozen hash or required
dependency is absent or mismatched. A failed preflight emits no scientific
verdict and does not consume the one execution authorization. After preflight
passes, the authorization is consumed before execution; any execution or
replay failure is final and cannot be retried.

## Mechanical verdict

The runner may emit only the frozen SC-3 values:

```text
GRI_SC3_ADVANTAGE
GRI_SC3_NO_ADVANTAGE
GRI_SC3_INCONCLUSIVE
```

No human selects the verdict afterward. The finite-state oracle remains a
reference and matching it does not count against Candidate B.

## Forbidden changes

Architecture, candidate source, candidate manifest, fixtures, split, budgets,
optimizer, decoder, precision rules, controls, ablations, development
search, retries, and post-result tuning are all forbidden.

## Boundary

```text
SC-3 CONTRACT:       FROZEN + VERIFIED
SC-3E AUTHORIZATION: ONE RUN
SCIENTIFIC RUN:      NOT STARTED
SCIENTIFIC RESULT:   NONE
```
