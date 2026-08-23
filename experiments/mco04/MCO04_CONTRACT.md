# MCO-04 — Opaque Real-Telemetry State-Compiler Replication Gate

## Claim under test

Complete machine telemetry can remain in an append-only evidence layer while a
transparent state compiler produces at most 16 auditable records that localize
the root-cause service on unseen telemetry runs. The bounded packet must
match or beat strong conventional RCA and hybrid-retrieval controls while using
materially less model context.

This is a product-mechanics claim. It is **not** a claim of general AI memory,
causal identification in arbitrary systems, or world-changing impact.

## Dataset and split

The benchmark is the 90-case RE3 suite of RCAEval, pinned by repository commit,
Hugging Face revision, and file hashes in `MCO04_CONFIG.json`. It contains raw
metrics and logs for all cases and traces where the source system records them.

- Engineering: every case whose public index has `repetition == 1` (27 cases).
- Scientific replication holdout: every case whose public index has
  `repetition != 1` (63 cases).
- No scientific file may be downloaded before the experiment freeze exists.
- Engineering observations may select one method before freezing. No method,
  threshold, window, capacity, prompt, or baseline may change afterward.

RCAEval source names encode the service and fault label. The staging layer must
therefore replace every source path with an opaque deterministic incident ID.
Only the scorer receives the source-name-to-label map. Compiler, retrieval,
reasoner, prompts, caches, and public artifacts may receive only opaque IDs,
telemetry, the alert/injection timestamp, and service names observed inside the
telemetry itself.

RCAEval is public and its index exposes labels, so this is executable isolation,
not a claim that the experimenter cannot know ground truth. Before freeze, an
automated literal audit must reject every scientific opaque ID and source-case
name from the method, prompt, configuration, and tests. The compiler and model
runs may not import or read scorer-only files. This limitation remains in the
assumption register even when the audit passes.

## Fixed compiler

For every metric, compare the 300 seconds before the alert with the 300 seconds
after it. The robust feature score is the largest absolute median, 10th
percentile, or 90th percentile shift divided by the maximum of:

1. baseline MAD scaled by 1.4826;
2. baseline IQR divided by 1.349;
3. standard deviation of baseline first differences divided by sqrt(2);
4. one percent of the absolute baseline median;
5. one tenth of one percent of the baseline 75th absolute percentile; and
6. `1e-8`.

Feature scores are capped at 30. Metric names are split only at their final
underscore into service and metric suffix. CPU, memory, socket, and disk-I/O
features are resource evidence. All others are symptom evidence.

For each service, sort feature scores descending. The service score is:

```text
resource_1 + resource_2
+ 0.25 * resource_3 + 0.25 * resource_4
+ 0.20 * symptom_1 + 0.20 * symptom_2
```

Missing positions contribute zero. Sort services by descending score and then
lexicographically for deterministic ties. No benchmark labels, source path, or
fault code enter this computation.

The evidence packet contains no more than 16 recomputable metric-shift records:
four resource plus two symptom records for the leading service, then up to two
records from each remaining service in rank order. Every record includes its
opaque evidence ID, source-file SHA-256, column, windows, point counts,
statistics, score, and aggregate digest.

## Controls

Run all controls on the same 63 incidents and alert timestamps:

1. author-style metric BARO from the pinned RCAEval implementation;
2. highest single robust feature shift;
3. highest post-onset error-like log volume;
4. lexical+dense hybrid RAG over fixed, label-blind telemetry chunks, retrieving
   at most 16 records and using the same frozen reasoner;
5. a maximum-safe-context reasoner baseline using a deterministic fixed-document
   prefix capped at 20,000 UTF-8 prompt bytes, with the actual model receipt
   required to keep maximum prompt plus maximum generated tokens below 8,192;
6. direct transparent compiler ranking; and
7. the same frozen reasoner over the compiler's at-most-16-record packet.

The compiler and retrieval controls receive identical raw modalities. The
hybrid control uses frozen EmbeddingGemma and reciprocal-rank fusion. Ground
truth may be read only after every prediction, packet, usage receipt, and
latency receipt for a case has been sealed.

The split holds out runs, not service/fault strata: each scientific case is a
new execution of a stratum represented once in engineering. This can establish
repeatability under telemetry noise. It cannot establish broad incident-class,
system, or benchmark generalization. The terminal label and interpretation are
therefore explicitly limited to **replication**.

## Primary and secondary measures

Primary quality is exact top-1 root-cause service. Report top-3, per-system
top-1, Wilson 95% intervals, and paired case-level differences.

Secondary measures are exact fault class, model diagnosis validity, exact
evidence provenance, packet-capacity compliance, raw and packet bytes, actual
model prompt/evaluation counts, wall time, model calls, embedding calls, and
replay/stability agreement. A model-generated citation is valid only if it names
an evidence ID in its supplied packet. Provenance integrity is recomputed from
the pinned source file; fluent unsupported explanations receive no credit.

The stability subset is the ceiling of 10% of scientific opaque IDs, selected
by the lowest SHA-256 values of the frozen seed and opaque ID. Each of the three
reasoning variants receives a fresh call from an isolated repeat cache. Semantic
agreement requires equality of validity, root-cause service, and fault class;
free-text wording and the particular valid citation subset do not define the
semantic outcome. Live/replay predictions must be byte-seal identical.

Reasoning-variant call order ranks opaque IDs by SHA-256 and assigns rotations
round-robin, so compiler, hybrid, and maximum-context calls differ by at most one
case in each position. Report model load, prompt evaluation, generation,
document-ingestion embedding, query embedding, retrieval CPU, and total online
query latency separately. Do not credit cached replay as fresh inference.
Local execution has zero billed API dollars, not zero compute cost; no unsupported
dollar estimate is manufactured. Tokens, calls, wall time, model-load time, and
the unknown nonzero pretrained-model training cost remain separate fields.

## Gates

The exact thresholds and outcome precedence live in `MCO04_CONFIG.json` and are
part of the freeze. In particular, the direct compiler must reach at least 90%
top-1 overall, 80% in every source system, 98% top-3, and a Wilson 95% lower
bound of 80%. Provenance and capacity compliance must both be 100%.

A quality win requires at least five percentage points over the strongest
control. A cost win requires quality within two points plus at least 10x fewer
actual model tokens and 2x lower latency. Context reduction by itself is not an
architecture win.

## Outcome semantics

- `MCO_04_BENCHMARK_INVALID`: source identity, split, opacity, provenance,
  replay, or accounting fails.
- `MCO_04_REAL_WORKLOAD_FAILURE`: the compiler misses a frozen quality,
  boundedness, or provenance gate.
- `MCO_04_CONVENTIONAL_RCA_DOMINATES`: a conventional control is equally or
  more accurate without a material cost/provenance disadvantage.
- `MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE`: the transparent
  compiler establishes repeatable mechanics on held-out executions, but bounded
  model inference adds no independently measured value.
- `MCO_04_BOUNDED_INFERENCE_REPLICATION_ADVANCE`: the bounded reasoner adds a frozen,
  material quality benefit beyond both the transparent compiler and strong
  controls while preserving cost and provenance gates.
- `MCO_04_INCOMPLETE`: required evidence is missing.

## Stop rule and interpretation

If conventional RCA dominates, stop claiming an AI-memory or state-compiler
architecture advantage on this workload. If either replication label advances,
the next required gate is a disjoint incident workload with held-out structures,
followed by an independently operated prospective pilot. A repeated-stratum
public benchmark cannot establish that the project will change the world.
