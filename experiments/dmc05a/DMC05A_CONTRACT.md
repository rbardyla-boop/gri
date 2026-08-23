# DMC-05A — Conventional Memory Null + Cost Scaling

Status: `PREREGISTERED_BEFORE_EXECUTION`

## Claim under test

Does the frozen DMC-04B pipeline retain a meaningful resource advantage on
the unchanged DMC-04B-A cases when compared with competent conventional
systems that may store all history externally and expose a bounded query
working set?

The strongest alternative explanation is:

> Ordinary exact structured storage or conventional bounded retrieval can
> preserve all history, match DMC-04B capability, and answer with no greater
> expensive working set or learned inference burden.

## Frozen candidate

DMC-04B is immutable for this experiment. DMC-05A may not retrain or alter its
retention scorer, associative retriever, decoder, features, thresholds,
capacity, tie breaks, benchmark cases, or metadata.

Frozen anchors:

```text
scripts/run_dmc04b.py:
3185434b9546236f93b3e75b47f5f11c88e7e33d89985a2c545c36c0fa90cbec

artifacts/dmc04b/DMC04B_VERDICT.json:
f62724ca065b166fbc00741f5097a24b85c36e1b232cfc67f6cccbb79c3ba902

artifacts/dmc04b/aggregate.json:
ffcceabec39c9953ec4617aecabd461ed1c6933a34612df08871424d79adb7ab

artifacts/dmc04ba/dataset_manifest.json:
ee4afa55326205030a8600b079a0a484b6bfa39312d6127a80633e00c93274fc
```

## Cases

Use every frozen DMC-04B-A case with write load in:

```text
32, 64, 128, 256, 1024
```

The expected frozen counts are 176, 160, 88, 80, and 88 respectively,
for 592 cases total. The eight load-512 cases are excluded because load 512
was not included in the requested DMC-05A scaling grid. No case is generated,
edited, or rebalanced.

## Competitors

### Full-history scan

Persist every original record. Inspect the full persisted history at query,
resolve the normalized two-attribute address and temporal mode exactly, and
make the full history query-visible.

### Recent window 16

Maintain the latest 16 writes with a conventional bounded deque. Resolve the
query exactly over that window.

### Frozen FIFO 16

Preserve the historical DMC-04B FIFO control exactly (`stream[:16]`). This is
reported separately from the conventional recent window because the frozen
control is not a latest-16 deque.

### Random 16

Preserve the frozen deterministic hash-ranked random control exactly.

### Exact structured external memory

Persist all records in a compact dictionary keyed by the normalized A/B
address already present in each write descriptor. Each version stores its
creation episode, record ID, and value. Query lookup may use the normalized
query descriptor and temporal mode directly. It receives no target record ID,
answer label, oracle view, or case ID.

### Conventional retrieval

Persist all records as compact normalized entries. At query, score records by
the number of matching normalized A/B attributes, use a frozen hash tie break,
return at most 16 candidates, and resolve temporal versions within those
candidates. It receives no target record ID, answer label, or oracle view.

### DMC-04B

Run the unchanged learned retention scorer online under the hard 16-record
capacity, then the unchanged paired learned associative retriever and fixed
seed-1337 decoder.

### DMC retriever over all history

Ablate learned retention only. Persist all records and apply the same paired
learned retriever and fixed decoder to the complete history without
retraining. Candidate-scoring volume is reported explicitly and is not
misreported as a bounded retrieval working set.

## Capability metrics

For every system, seed where applicable, history size, and case:

```text
critical recall
retrieval accuracy
answer accuracy
```

Critical recall means that the exact target record survives persistence or is
present in the bounded retrieved candidate set, whichever boundary applies to
the system.

## Resource metrics

Record absolute values, not a composite score:

```text
persistent record count
persistent canonical serialized bytes
records inspected during ingestion
records inspected at query
retrieval candidate records
retrieved records
write operations
update/supersession operations
retrieval/index operations
maximum query working-set records
query working-set canonical serialized bytes
ingestion wall time
query wall time
worker wall time
worker peak RSS
retention model forward calls
retrieval model forward calls
decoder model forward calls
```

Canonical byte accounting is UTF-8 JSON with sorted keys and no insignificant
whitespace. Timing uses `perf_counter_ns`; checkpoint loading, frozen fixture
parsing, and receipt serialization are excluded from online ingestion/query
timing. Worker wall time and peak RSS are also recorded separately and include
process/runtime overhead.

The benchmark is synthetic and has no applicable language tokenizer.
`model_visible_tokens` must therefore be `NOT_APPLICABLE_SYNTHETIC_RECORDS`,
never zero or an invented token estimate.

## Training accounting

DMC online execution uses frozen models, but their training is charged.
DMC-05A reconstructs every quantity supported by frozen receipts:

- DMC-01 fixed decoder: epochs, cases, batches, optimizer steps, parameters;
- DMC-03 retention scorer: epochs, examples, batches, optimizer steps,
  parameters;
- DMC-04R2 retriever: epochs, cases, batches, optimizer steps, parameters.

Historical wall time, energy, and dollar cost were not recorded. Those fields
must be `TRAINING_COST_UNKNOWN`. Structural training counts and per-evaluation
case amortization are reported separately; they may not be converted into a
currency estimate.

## Gates

Frozen thresholds:

```text
DMC capability threshold:                    >= 0.99
strong conventional capability threshold:    >= 0.99
maximum capability match gap:                 <= 0.01
DMC persistent-byte ratio at load 1024:       <= 0.10
bounded query/model-visible candidate limit:  <= 16
DMC all-history ablation gap:                 <= 0.01
```

## Mechanical verdict precedence

1. `DMC_05A_ACCOUNTING_INVALID`
   if any frozen anchor, case count, capacity, leakage, replay, byte
   accounting, training-accounting status, or required metric is invalid.
2. `DMC_05A_BOUNDED_MEMORY_ADVANTAGE`
   if DMC passes capability while both exact structured memory and
   conventional retrieval fail the capability threshold or exceed the
   bounded query-visible limit.
3. `DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES`
   if a matching conventional system is no worse in persistent bytes, query
   working bytes, query work, and online wall time, and requires no learned
   training.
4. `DMC_05A_STORAGE_ONLY_ADVANTAGE`
   if exact structured memory and conventional retrieval match DMC capability
   with bounded query-visible state, DMC reduces persistent bytes by at least
   90% at load 1024, and removing learned retention causes at most a 0.01
   capability loss.
5. `DMC_05A_TRADEOFF`
   for a valid non-dominating comparison in which systems win different
   absolute resource dimensions.

No DMC-05B, language benchmark, architecture modification, or threshold
change is authorized by this contract.
