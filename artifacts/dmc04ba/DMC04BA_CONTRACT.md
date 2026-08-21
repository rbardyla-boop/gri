# DMC-04B-A — Integrated Bounded Memory Benchmark

Status: **STRUCTURAL BENCHMARK ONLY; NO TRAINING; NO SCIENTIFIC EVIDENCE RUN**

DMC-04B-A integrates the frozen DMC-02A/DMC-03 retention interface, the
frozen DMC-04A/DMC-04R2 associative descriptor interface, and the fixed native
seed-1337 decoder. Each case contains more than 16 experienced writes, but
exactly 16 records satisfy the benchmark-authorized retention predicate. Only
those 16 records enter `neural_view`; the experience stream is benchmark input,
not an archive or spill path.

The only retention features are `[mission_membership, high_salience]`. The
retention path receives `RetentionMetadata` and active scope only. The retrieval
path receives the frozen DMC-04R2 scorer view: disjoint write/query A/B
descriptors and creation episode. No logical key, answer, value, record ID,
query identity, or hidden vector enters either learned interface.

All hidden vectors are generated from the unchanged native DMC-01 exact
seed-1337 checkpoint (`4d7dd38a...c99b35a6`). All five frozen DMC-03 scorers
and DMC-04R2 retrievers are loaded read-only for compatibility checks. This
unit executes zero optimizer steps, zero backward passes, and zero evidence
training.

## Frozen structural gates

- Physical memory budget: 16 records; every case has >16 writes and exactly
  16 post-retention candidates.
- Oracle retention, symbolic associative retrieval, and fixed decoder each
  achieve 1.0 on every split.
- DMC-03 and DMC-04R2 interfaces consume every integration case without
  adapters, feature additions, retraining, or checkpoint mutation.
- Query/write codebooks remain disjoint; neural projections contain no oracle
  fields; deterministic generation is byte-identical on replay.
- FIFO, random-retention, exact-token, A-only, and B-only controls provide a
  nontrivial structural signal.

The future scientific DMC-04B factorial comparison and its gates are frozen
in `DMC04BA_CONFIG.json` but are not executed here. The next unit may compare
learned DMC-03 retention with learned DMC-04R2 retrieval against the listed
controls using the paired seeds 1337–1341.

No DMC-05, consolidation, forgetting, compression, additional dimensions,
language expansion, or architecture redesign is authorized by this unit.
