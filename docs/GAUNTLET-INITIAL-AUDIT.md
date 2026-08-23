# Gauntlet Initial Audit — Externalized Persistent State

## Scope

This is the initial audit requested by the machine-cognitive-offloading
gauntlet. It records the repository state before expanding the architecture.
Existing files and local worktree changes were preserved.

## Current scientific state

The repository is a mature experimental laboratory, but it is not yet a
demonstration of long-running AI reasoning with externalized state.

Established bounded results:

- WORLD-0 is deterministic, replayable, and has frozen relational reasoning
  fixtures and controls.
- Generic transform-every-step recurrence failed the GRI-01 diagnostic
  sequence under long no-op delays, precision stress, and a fixed decoder.
- An explicit preserve/transform recurrent mechanism solved that bounded
  fixture family, but its formal resource advantage was revoked after selector
  accounting (`GRI-02C.1`).
- Learned retention (DMC-03) and learned associative retrieval (DMC-04R2)
  each have frozen five-seed evidence on their own benchmark families.
- DMC-04B-A freezes an integrated 16-record memory benchmark with 600 cases,
  paired seeds, adversarial load families, oracle/FIFO/random controls,
  component firewalls, restart, replay, and a fixed decoder.
- The KC branch is closed after a negative equal-budget utility result; it is
  development infrastructure, not evidence for useful AI memory.

Not established:

- a practical token or dollar advantage over a strong full-context, sliding
  window, rolling-summary, or RAG baseline;
- long-horizon scaling to thousands or tens of thousands of events;
- model-independent memory interoperability;
- safe lossy compression, surprise-dependency retention, or automatic
  contradiction/update handling in realistic reasoning workloads;
- minimality, a lower bound, or any broad cognitive claim.

## Claim under test

> Under the frozen DMC-04B-A workload, independently trained bounded
> retention and retrieval components can compose under a hard 16-record
> external memory and retain competitive task performance across the five
> paired evidence seeds, including the high-load and supersession cases.

This is deliberately narrower than the program-level claim. It tests
composition and bounded active state, not general reasoning or cost advantage.

## Strongest existing baseline

For this first discriminator, the strongest correctness counterfactual is the
`oracle_retention + oracle_retrieval` mode. The strongest practical controls
are `FIFO + learned retrieval`, `random retention + learned retrieval`, and
`learned retention + random retrieval`. Earlier units also provide exact,
random, and token controls for retrieval.

These are not yet the full gauntlet baselines. Full-context, sliding-window,
rolling-summary, and conventional RAG cost baselines remain unimplemented in
this repository.

## Largest uncertainty

The largest immediate uncertainty is whether learned selection survives
composition: retention and retrieval may each work in isolation while their
errors interact under one bounded working set. The larger program-level
uncertainty is whether any such capability survives realistic cost accounting
and history growth.

## Cheapest discriminating experiment

Run the existing frozen harness:

```bash
python3 scripts/run_dmc04b.py
```

The harness must pass its repository preflight, verify frozen predecessor and
checkpoint identities, evaluate 600 cases across five paired seeds and seven
modes, enforce the 16-record capacity, check input firewalls and component
immutability, replay seed 1337, and emit:

```text
artifacts/dmc04b/DMC04B_VERDICT.json
artifacts/dmc04b/DMC04B_REPORT.md
artifacts/dmc04b/aggregate.json
artifacts/dmc04b/replay.json
```

The mechanical terminal states are defined in `scripts/run_dmc04b.py`. No
manual threshold or post-result interpretation is permitted.

## Verification contract

### Criteria

- Engineering preflight: repository tests and frozen identities pass.
- Capacity: no mode exceeds 16 active records.
- Leakage: retention and retrieval interfaces receive no answer, value,
  logical key, record ID, query identity, or hidden vector.
- Integration: learned retention plus learned retrieval reaches the frozen
  performance gates and does not exceed the oracle gap.
- Attribution: FIFO/random-retention/random-retrieval controls separate the
  claimed mechanisms.
- Reproducibility: component hashes remain unchanged and seed-1337 replay is
  byte-identical.

### Verdict language

The run completed with `DMC_04B_COMBINED_LEARNED_MEMORY_ADVANCES`.

Observed evidence:

- learned retention + learned retrieval: `P_R = 1.000`, `P_answer = 1.000`
  on each of five paired seeds;
- all seven high-load components: `1.000`;
- FIFO + learned retrieval: `P_R = 0.000`;
- random retention + learned retrieval: `P_R = 0.000`;
- learned retention + random retrieval: `P_R = 0.0725`;
- all integrity gates, the 16-record capacity bound, interface firewalls,
  component immutability, and seed-1337 replay: PASS.

Therefore the bounded composition claim is `SCIENTIFIC_ADVANCE`. The
program-level externalized-reasoning claim remains `ADVANTAGE_NOT_ESTABLISHED`:
this run measured neither inference cost nor history scaling, and it used a
synthetic fixed-decoder workload.

## Assumption register

| Assumption | Status | Evidence or missing check |
|---|---|---|
| Frozen benchmark and predecessor artifacts are intact | Checkable | DMC-04B identity and manifest checks |
| Learned interfaces exclude oracle fields | Checkable | DMC-04B retention/retrieval firewalls |
| Active memory remains bounded | Checkable | DMC-04B capacity audit |
| Component errors compose favorably | Checkable | DMC-04B paired-mode gates |
| Result is replayable | Checkable | DMC-04B replay artifact |
| Capability is cheaper than conventional alternatives | Unchecked | No token/call/latency/cost baselines yet |
| Capability scales with history while active state stays bounded | Unchecked | No long-history scaling curve yet |
| Representation transfers across models | Unchecked | No model-swap test yet |

## Credit assignment

The first run changes no architecture. If it passes, credit is attributable to
the already-frozen composition of DMC-03 retention and DMC-04R2 retrieval only
when the single-mechanism controls and replay also pass. If the run fails,
the next diagnosis must distinguish implementation, benchmark, interface,
retention, retrieval, and interaction failure before any change is made.

## Verification gap and continuation

This first discriminator did not instrument model tokens, call counts,
latency, storage bytes, or cost against conventional baselines. The next
bounded experiment should add those accounting fields and a history-scaling
workload, with full-context, sliding-window, rolling-summary, and conventional
RAG controls. No architecture expansion is justified before that comparison.

## Maturity status

The DMC-04B-A candidate is defined, specified, testable, falsifiable, replayable,
and comparable against frozen variants. It is mature as a bounded integration
experiment. The broader externalized-reasoning hypothesis remains a
long-horizon claim and is not mature.
