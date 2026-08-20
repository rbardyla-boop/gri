# DMC-00 — Memory-Need Benchmark

Status: **PREREGISTERED; BENCHMARK ONLY; NO MEMORY ARCHITECTURE; NO TRAINING**

## Goal

DMC-00 measures information that must survive between separate episodes. It
is deliberately distinct from WORLD-0/RRI, where all useful facts are present
inside one graph example.

The benchmark has four primitive families:

- `M0-A delayed_recall`: delays 1, 4, 16, 64, 256, 1024 episodes.
- `M0-B supersession`: current and historical retrieval after a later write.
- `M0-C distractor_resistance`: loads 0, 8, 32, 128, 512, 1024.
- `M0-D capacity_pressure`: loads 4, 16, 64, 256, 1024.

Each condition has 16 deterministic cases balanced across eight values. Query
episodes contain only a query; the answer value is never present there.

## Event ledger

Writes record `memory_id`, entity, field, value, creation episode, and
supersession provenance in the independent oracle ledger. Historical entries
are retained. Current queries return the latest eligible entry; history queries
return the latest entry at the requested source episode.

## Splits

- Train: delays 1/4/16, distractors 0/8/32, capacity 4/16/64.
- IID: same regime with deterministic cases from the IID split.
- Extrapolation: delays 64/256/1024, distractors 128/512/1024, capacity 256/1024.

No model is trained during DMC-00. These splits define the later DMC-01
experiment.

## Information firewall

The current episode is one query event with no value, answer, memory ID, or
case ID. Query projections are balanced over all eight values. Opaque entity
tokens contain no value text, query episode lengths are constant, and split
content hashes are disjoint. The current-episode-only control sees only the
final query episode and is expected to perform at the 1/8 class prior.

## Future metric

Frozen before any memory model is trained:

```text
P_memory = mean(R64, R256, R1024, C256, C1024,
                S_current, S_history, D512, D1024)
```

## Stop states

- `DMC_00_MEMORY_BENCHMARK_PASS`
- `DMC_00_MEMORY_LEAK`
- `DMC_00_ORACLE_INVALID`
- `DMC_00_INVALID`
- `DMC_00_REPAIR_REQUIRED`

DMC-00 stops after validation. DMC-01 is not implemented here.
