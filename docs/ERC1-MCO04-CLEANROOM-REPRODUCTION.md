# ERC-1 — Clean-room MCO-04 Direct-Compiler Reproduction

Status: PREREGISTERED PRE-EXECUTION
Date: 2026-08-23

## 1. Purpose

Independently reimplement and reproduce the narrow positive mechanical result reported by MCO-04 without importing or reading the original MCO-04 runner implementation.

This experiment does not reopen the terminal GRI/DMC/MCO transferable-architecture claim. It tests only whether the published deterministic MCO-04 compiler formula independently reproduces its reported RCAEval RE3 service-localization result.

## 2. Historical target

The previously frozen MCO-04 record reports that the direct transparent compiler localized the root-cause service in all `63/63` scientific RE3 cases, where:

- engineering cases were public-index `repetition == 1`;
- scientific cases were `repetition != 1`;
- scientific cases were unseen executions of service/fault strata already represented in engineering;
- packet capacity was at most 16 records;
- this was a replication result, not disjoint incident-class generalization.

ERC-1 attempts an independent mechanical reproduction of the direct compiler only. No language model is needed.

## 3. Clean-room firewall

Allowed design sources before implementation:

- `experiments/mco04/MCO04_CONTRACT.md`;
- `experiments/mco04/MCO04_CONFIG.json`;
- `experiments/mco04/MCO04_FREEZE.json` only for historical source/data bindings and reported environment identity;
- public RCAEval documentation and the pinned RCAEval reader/data format.

Forbidden as implementation sources:

- `scripts/run_mco04.py`;
- `tests/test_mco04.py`;
- MCO-04 per-case prediction files, scored rows, or scorer internals;
- copying any MCO-04 compiler implementation code into ERC-1.

The ERC-1 source tree must not import the forbidden runner or original MCO-04 test module. CI mechanically checks this boundary.

## 4. Dataset identity

Historical bindings from MCO-04:

- RCAEval repository commit: `4695aa69f4f1f57b9094ca04ff235908b73a8e24`;
- historical Hugging Face dataset revision: `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e`;
- historical public index SHA-256: `c49a288920dbba2e8e724679a14636d5c7eb2b45426bba14007ef79a6c0ab1bb`;
- suite: RE3;
- expected cases: 90;
- expected scientific cases: 63.

The public RCAEval project later published a Parquet repackaging and states that it is value-for-value lossless relative to the original `metrics.json` representation. ERC-1 therefore distinguishes two evidence classes:

### A. EXACT_SOURCE_REPRODUCTION

The operator supplies the exact historical source representation/revision and its source manifest passes the historical binding checks available to ERC-1.

### B. LOSSLESS_REPACK_REPRODUCTION

The operator supplies the later RCAEval Parquet representation for the same 90 RE3 cases. The result may test independent mechanical reproducibility of the published formula, but it must not be described as byte-identical source reproduction.

No other dataset representation is silently accepted.

## 5. Opacity boundary

RCAEval case names encode root service and fault. ERC-1 therefore stages telemetry into opaque case files before compilation.

Staging produces two physically separate directories:

- `candidate/`: opaque IDs, metrics, injection timestamp, source-content hash, source-system code;
- `scorer_only/`: opaque-ID -> original case name, root service, fault, repetition, system.

The compiler receives only `candidate/`.

The scoring process runs only after predictions and packet hashes are sealed.

This is executable isolation on a public benchmark, not experimenter blinding.

## 6. Independent compiler formula

For every metric column:

- use the 300 seconds immediately before injection;
- use the 300 seconds beginning at injection;
- require at least 20 finite observations in each window;
- compute the absolute shifts in median, 10th percentile, and 90th percentile;
- numerator = largest of those three shifts;
- denominator = maximum of:
  1. `1.4826 * baseline MAD`;
  2. `baseline IQR / 1.349`;
  3. `std(diff(baseline), population) / sqrt(2)`;
  4. `0.01 * abs(baseline median)`;
  5. `0.001 * baseline 75th percentile of absolute values`;
  6. `1e-8`;
- score = `min(30, numerator / denominator)`.

Metric names are split only at the final underscore. The suffixes `cpu`, `mem`, `socket`, and `diskio` are resource evidence; every other suffix is symptom evidence.

For each service, descending feature scores are aggregated as:

```text
resource_1 + resource_2
+ 0.25 * resource_3 + 0.25 * resource_4
+ 0.20 * symptom_1 + 0.20 * symptom_2
```

Missing positions contribute zero. Services sort by descending aggregate score and then lexical service name.

No ground-truth service, fault code, source path, or case name may enter the computation.

## 7. Packet reconstruction

For the leading service, retain its four highest resource records plus two highest symptom records.

Then visit remaining services in predicted rank order and add up to their two highest feature records until the packet reaches 16 records.

Each retained feature record contains enough statistics to recompute its score plus:

- opaque case ID;
- metric column;
- service/suffix;
- source-content SHA-256;
- pre/post window bounds;
- finite point counts;
- numerator statistics;
- denominator components;
- feature score;
- packet digest.

Capacity >16 or provenance mismatch is a reproduction integrity failure.

## 8. Reproduction targets

Primary exact target:

- scientific case count = 63;
- compiler top-1 = `63/63`;
- overall top-3 = `63/63`;
- every source system top-1 = `1.0`;
- packet capacity compliance = `1.0`;
- source/provenance recomputation = `1.0`;
- deterministic replay = `1.0`.

This experiment uses exact equality to the reported `63/63` mechanical result. `62/63` is a discrepancy, not a successful reproduction.

Secondary diagnostics include engineering `repetition == 1` performance, per-case service rankings, packet sizes, and disagreement cases. These do not alter the reproduction criterion.

## 9. Outcome precedence

1. `ERC1_SOURCE_IDENTITY_INVALID`
2. `ERC1_OPACITY_OR_PROVENANCE_INVALID`
3. `ERC1_CLEANROOM_DISCREPANCY`
4. `ERC1_MCO04_DIRECT_REPRODUCED_LOSSLESS_REPACK`
5. `ERC1_MCO04_DIRECT_REPRODUCED_EXACT_SOURCE`
6. `ERC1_INCOMPLETE`

The evidence-class suffix matters. A lossless-repack reproduction cannot be represented as exact historical source-byte reproduction.

## 10. Stop rule

If the clean-room compiler does not reproduce `63/63`, preserve every disagreement and investigate implementation/data-definition differences without changing the formula and rerunning the same cases as a rescue attempt.

If it reproduces, freeze the clean-room implementation and run it again from a fresh checkout/operator environment. Only after that is cross-domain transfer justified.

No ERC-1 result establishes general AI memory, semantic understanding, arbitrary causal discovery, product value, or world impact.
