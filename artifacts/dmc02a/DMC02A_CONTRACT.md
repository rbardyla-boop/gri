# DMC-02A — Selective Retention Benchmark

Status: **BENCHMARK ONLY; NO BOUNDED MEMORY ARCHITECTURE; NO TRAINING**

## Claim under test

The DMC-02A exam is a fair, deterministic selective-retention benchmark:
each intended condition is solvable with a hard 16-record budget using only
legitimate future-utility signals, while FIFO and deterministic random
retention materially degrade at extrapolated loads.

DMC-00 remains unchanged. DMC-01 remains an unbounded exact-memory control;
its learned models are not retrained here.

## Frozen budget and value space

- Physical record budget: **16** per case.
- Values: RED, BLUE, GREEN, YELLOW, ORANGE, PURPLE, BLACK, WHITE.
- Each condition has 16 cases, with exactly two cases per answer class.
- The final query episode contains exactly one query event and no answer value,
  memory ID, or case ID.

## Families

- **B2-A mission_set:** a 16-entity mission set is announced before writes;
  loads are 32/64 for train and IID, and 128/256/1024 for extrapolation.
- **B2-B salience:** exactly 16 HIGH writes are mixed with LOW writes;
  the query targets a HIGH record. Loads use the same split allocation.
- **B2-C supersession:** eight mission entities receive original and current
  writes, retaining 16 queryable historical/current records. Loads use the
  same split allocation; current and history are separate conditions.
- **B2-D utility_change:** phase A announces 16 keys, then a mission update
  announces phase B before phase-B writes. Overlaps are 0/25/50/75/100%.
  Training and IID use 0/50/100%; extrapolation includes all five, thereby
  holding 25% and 75% out from training. Loads use the same allocation.
- **B2-E distractor_flood:** 16 HIGH relevant writes precede LOW irrelevant
  writes. Distractor counts are 0/32 for train and IID, and 128/512/1024 for
  extrapolation.

For utility change, the benchmark includes 16 phase-B records and discards
obsolete phase-A records only after the explicit mission update. Thus the
minimum simultaneous useful record count is 16, including at 0% overlap.

## Oracles and controls

The unbounded oracle retains every write and must score 100%.

The bounded oracle has capacity 16 and may inspect only mission-set
membership, salience, mission updates, and supersession metadata. It never
uses the hidden answer or the future query choice. It must score at least
0.99, with 1.0 expected.

FIFO is a deterministic 16-record first-in-first-out ledger. Random retention
is a deterministic reservoir-style 16-record controller with independent
control seed `20260202`. At extrapolated load conditions, the bounded-oracle
primary metric must exceed each control by at least 0.40.

## Frozen primary metric

Each named component is a case-weighted mean within its exact condition.
`SHIFT` is the equal-weight mean over utility-change overlaps at load 1024.
The future bounded-memory metric is:

```text
P_bounded = mean(
    M256, M1024,
    SAL256, SAL1024,
    SUP_current_1024, SUP_history_1024,
    SHIFT,
    FLOOD512, FLOOD1024
)
```

The same metric is reported for FIFO and random retention. No model result
is produced by this unit.

## Information-theoretic accounting

Every case records total writes, query-eligible records, physical budget, and
minimum records required by the intended optimal strategy. Any case requiring
more than 16 records invalidates generation.

## Terminal states

- `DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS`
- `DMC_02A_CAPACITY_INVALID`
- `DMC_02A_MEMORY_LEAK`
- `DMC_02A_ORACLE_INVALID`
- `DMC_02A_RETENTION_SIGNAL_WEAK`
- `DMC_02A_INVALID`
- `DMC_02A_REPAIR_REQUIRED`

This unit stops after the benchmark receipt. It does not implement learned
retention, eviction, compression, learned retrieval, dimensional metadata,
consolidation, forgetting, or any training/evidence seeds.
