# ERC-2A — DAMADICS Structural Transfer

Status: PRE-DATA PREREGISTRATION

## Purpose

ERC-2A is the first strict cross-domain transfer test of the deterministic compiler that independently reproduced the historical MCO-04 root-service result in ERC-1B.

ERC-1B terminal evidence:

- frozen compiler SHA-256: `2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d`
- scientific localization: 63/63 top-1, 63/63 top-3
- engineering diagnostic: 27/27 top-1
- prediction seal: `77ddb6e98facad0d5862234de69b64a92dc56951e28dae656e0b18bd3c760196`
- reproduction report SHA-256: `6abc9b0c1687ed68fc2ba844c58912a9f7a17d5b564f855c84a5e76eeae29138`
- workflow run: `32668812984`

ERC-2A does **not** ask whether the compiler can be improved for a new domain. It asks whether the byte-identical compiler transfers without changing its scoring mathematics.

## Pre-screened alternative rejected before execution

The Rieth Tennessee Eastman Process dataset was considered first. It is sampled every 180 seconds, while the frozen compiler requires at least 20 finite points in each 300-second pre/post window. A strict transfer would therefore produce no eligible feature records unless time were rescaled, interpolated, or the compiler window/minimum-point rule were changed.

TEP is therefore rejected as the first strict transfer workload before any ERC-2 scientific execution. It may later be used only in a separately disclosed time-normalized successor.

## Dataset

ERC-2A uses the public DAMADICS actuator benchmark operational data from the Lublin Sugar Factory.

Authoritative source page:

`https://iair.mchtr.pw.edu.pl/Damadics`

The official benchmark provides:

- daily process files from 2001-10-27 through 2001-11-23;
- first column = seconds from midnight;
- a separate data-file-description package mapping columns to process variables;
- a benchmark-definition package containing the report of artificially introduced faults.

Published benchmark literature independently describes the real-data collection as approximately 1 Hz and 32 process variables, with artificial fault events inserted on four days: 2001-10-30, 2001-11-09, 2001-11-17 and 2001-11-20.

## Target

For each officially documented artificial single-actuator fault event, predict **which physical actuator was disturbed**:

- `A1`
- `A2`
- `A3`

Fault type (`f16`–`f19`), date, source event description and source actuator identity are scorer-only metadata.

The target is actuator localization, not 19-way fault-type classification.

## Event schedule rule

The official benchmark-definition fault report is the only authoritative event schedule.

Before any telemetry is made candidate-visible, the metadata qualification stage must:

1. retrieve the official benchmark-definition archive;
2. hash the archive and the extracted fault-report source;
3. parse every artificially introduced real-process fault event;
4. require exactly 19 events across the four published fault days;
5. bind for every event: date, actuator identity, fault code, event start, event end;
6. require a complete 300-second pre-window and 300-second post-window around event start;
7. require no second artificial fault event to overlap that 600-second analysis window.

If the official report cannot be parsed unambiguously, the count is not 19, an actuator label is missing, or any analysis window is confounded, terminate pre-prediction as:

`ERC2A_SCHEDULE_QUALIFICATION_FAIL`

No manual event deletion is permitted after telemetry performance is observed.

## Column-mapping rule

The official DAMADICS data-file-description package is the only authoritative column map.

The adapter must identify the six canonical actuator-local signals documented by the benchmark for each actuator:

- control value `CV`
- inlet pressure `P1`
- outlet pressure `P2`
- liquid temperature `T1`
- stem/rod displacement `X`
- flow `F`

Qualification must require exactly one `CV`, `P1`, `P2`, `T1`, `X`, and `F` assignment for each of `A1`, `A2`, and `A3`.

Every uniquely actuator-local canonical signal is used exactly once. Shared/global plant variables are excluded because they do not belong uniquely to a candidate actuator.

No signal may be selected or omitted based on observed event performance.

## Adapter transformation

For each event the adapter may perform only:

1. numeric parsing;
2. timestamp preservation in real seconds from midnight;
3. extraction of `[event_start - 300, event_start + 300)`;
4. deterministic renaming of the six local signals per actuator to generic names:
   - `A1_sig01` ... `A1_sig06`
   - `A2_sig01` ... `A2_sig06`
   - `A3_sig01` ... `A3_sig06`
5. deterministic ordering;
6. lossless serialization to the compiler's staged Parquet contract.

The adapter may **not**:

- smooth;
- interpolate;
- resample;
- impute;
- normalize values;
- derive residuals;
- add engineered features;
- use the fault code to transform data;
- use the target actuator to transform data;
- change timestamps;
- map any signal to `cpu`, `mem`, `socket`, or `diskio` suffixes.

All adapted signals therefore enter the frozen compiler through its generic `symptom` path.

## Frozen compiler

`experiments/erc1/compiler.py` must remain byte-identical with SHA-256:

`2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d`

The following remain unchanged:

- 300-second pre-window;
- 300-second post-window;
- minimum 20 finite points per side;
- median/P10/P90 shift numerator;
- MAD/IQR/difference-noise denominator;
- scale floors;
- score cap 30;
- service/entity aggregation weights;
- packet capacity 16;
- deterministic ranking/tie-breaking.

Any compiler change creates a different experiment and invalidates ERC-2A.

## Candidate/scorer isolation

Candidate-visible event data contain only:

- opaque event ID;
- event start time;
- 18 adapted actuator-local signals;
- source/staged byte hashes.

The candidate side must not contain:

- calendar date;
- original source filename;
- fault code;
- fault description;
- true actuator identity;
- original DAMADICS signal names.

The scorer map remains physically separate until live and replay prediction seals exist.

## Transparent baseline

ERC-2A includes one mandatory simplicity baseline computed from the same adapted values and the same frozen feature-score formula:

`LARGEST_SINGLE_SHIFT`

For each actuator, take its maximum individual normalized feature score. Rank actuators by that value with lexical tie-break.

This baseline receives no multi-signal corroboration.

It is specified before telemetry scoring and cannot be changed after execution.

## One-shot criteria

Primary scientific event count: 19.

### `ERC2A_STRICT_TRANSFER_PASS`

Requires all of:

- event schedule qualification PASS;
- column-map qualification PASS;
- compiler SHA PASS;
- live/replay prediction bytes identical;
- provenance/capacity checks PASS;
- ERC actuator top-1 = 19/19;
- every target actuator represented in the official schedule is perfect;
- `LARGEST_SINGLE_SHIFT` top-1 <= 17/19.

### `ERC2A_TRANSFER_PASS_SIMPLE_RULE_SUFFICIENT`

Requires:

- all integrity conditions above;
- ERC top-1 = 19/19;
- baseline top-1 >= 18/19.

Interpretation: the cross-domain localization phenomenon transfers, but the extra corroboration machinery has not earned distinct mechanism credit.

### `ERC2A_TRANSFER_DISCREPANCY`

Any valid run with ERC top-1 < 19/19.

`18/19` is a discrepancy. There is no threshold relaxation after execution.

### Integrity-invalid states

Source, schedule, mapping, opacity, provenance, replay, or compiler-hash failures are integrity/mechanical failures and are not scientific transfer results.

## Scale rule

There is no tuning loop after ERC-2A.

If ERC-2A reaches either strict transfer PASS state, the next experiment may scale within DAMADICS or move to a third domain, but it must be separately preregistered before observing additional target-labelled performance.

If ERC-2A produces a valid discrepancy, the 19 event errors are analyzed as evidence. The compiler is not modified and rerun on the same event set.

## Nonclaims

Even a strict PASS does not establish:

- general causal inference;
- universal root-cause diagnosis;
- semantic understanding;
- consciousness;
- AGI;
- superiority over learned process-diagnosis methods.

A PASS would establish only that the frozen deterministic witness compiler transferred from RCAEval microservice telemetry to this preregistered DAMADICS physical-actuator localization task under the stated adapter and integrity constraints.

## Execution state at preregistration

- DAMADICS telemetry downloaded by ERC-2A: **NO**
- event schedule qualified: **NO**
- column map qualified: **NO**
- adapter implemented: **NO**
- ERC-2A predictions: **0**
- scorer opened: **NO**
- scientific model calls: **0**
