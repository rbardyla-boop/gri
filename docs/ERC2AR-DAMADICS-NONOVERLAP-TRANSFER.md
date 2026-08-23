# ERC-2AR — DAMADICS Non-Overlap Structural Transfer

Status: PRE-TELEMETRY PREREGISTRATION

## Why this successor exists

ERC-2A was preregistered to use all 19 officially documented artificial DAMADICS fault events only if every event admitted an uncontaminated 300-second pre-window and 300-second post-window.

ERC-2A terminated before plant telemetry as:

`ERC2A_SCHEDULE_QUALIFICATION_FAIL`

Exact predecessor qualification:

- head: `faebf1dc3dc44fedc4a8d56c8f116e9229b39706`
- workflow run: `32673991129`
- official events: 19
- signal-map qualification: PASS
- clean windows: 13
- confounded windows: 6
- qualification record SHA-256: `9b77ac9103d43889b379839609c6a51e9245c88c855cbb4d1e2f38350260769c`
- telemetry downloaded: 0
- predictions: 0

ERC-2AR is a separately disclosed successor. It does not redefine the predecessor result. It freezes the subset mechanically produced by the predecessor's already-preregistered exclusion rule before any plant telemetry is observed.

## Frozen event set

The scientific event set is exactly the predecessor's `clean_events` set:

`[1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 19]`

No event may be added, removed, substituted or reclassified after telemetry is acquired.

Target distribution from the official schedule:

- A1: 6 events — `[1,2,4,5,6,7]`
- A2: 5 events — `[8,9,10,11,13]`
- A3: 2 events — `[14,19]`

The six predecessor-confounded events `[3,12,15,16,17,18]` are not scientific observations in ERC-2AR. They remain documented exclusions and may not be used for tuning, threshold selection or error repair.

## Claim under test

> The byte-identical deterministic compiler that reproduced 63/63 RCAEval root-service localizations can, under a purely structural schema adapter, localize the physically disturbed DAMADICS actuator on all 13 preregistered non-overlapping real-plant artificial-fault events.

This is a strict structural-transfer claim, not a general causal-inference claim.

## Dataset authority

The only allowed telemetry source is the official DAMADICS benchmark site:

`https://iair.mchtr.pw.edu.pl/Damadics`

The four official archive URLs are frozen before download:

1. `https://iair.mchtr.pw.edu.pl/content/download/163/817/file/Lublin_all_data_part1.zip`
2. `https://iair.mchtr.pw.edu.pl/content/download/164/821/file/Lublin_all_data_part2.zip`
3. `https://iair.mchtr.pw.edu.pl/content/download/165/825/file/Lublin_all_data_part3.zip`
4. `https://iair.mchtr.pw.edu.pl/content/download/166/829/file/Lublin_all_data_part4.zip`

The official page states that these archives contain daily Lublin Sugar Factory data from 2001-10-27 through 2001-11-23 and that the first column is seconds from midnight.

The already-qualified official metadata bindings remain:

- benchmark-definition ZIP SHA-256: `216bdd72e1b6ee1ebf77d8ed2609f67a8ce5cdc806cf9f288e067ccfb6be6e04`
- data-description ZIP SHA-256: `ee6f4083fae635c34bd6e33b068553a401e9e182e50f0914c5956f3073b7625a`
- data-description PDF SHA-256: `11aad05df27793a10baaa5e12c1a78ee946b0d67fb70f65c706183946c7be8de`
- extracted data-description text SHA-256: `b64326a26781305d179efcf170e9a051ca6b498a9e7d24e086425e47bccd35f7`

## Data-binding qualification before prediction

The first successor stage may download the four telemetry ZIP archives only to establish source identity and inventory.

It must:

1. record SHA-256 for every ZIP;
2. record every ZIP member path, byte size and CRC;
3. identify exactly one daily source file for each of the four fault dates:
   - 2001-10-30
   - 2001-11-09
   - 2001-11-17
   - 2001-11-20;
4. verify each selected daily file has exactly 86,400 non-empty records;
5. verify each record has exactly 33 columns;
6. verify column 1 is numeric seconds from midnight and covers 0..86,399 in strict order;
7. hash each selected raw daily file before parsing values.

This stage may validate shape and timestamp identity but may not compute any feature scores, event performance, actuator ranking or target-conditioned statistics.

Any ambiguity or shape failure terminates pre-prediction as:

`ERC2AR_DATA_BINDING_FAIL`

No mirror or alternate dataset may be substituted inside the same experiment.

## Frozen official actuator-local column map

Only the 18 canonical local signals already qualified from the official data-description PDF are candidate-visible.

Canonical order per actuator is fixed as:

`P1, P2, T1, F, CV, X`

A1:

- P1 = `P51_05`
- P2 = `P51_06`
- T1 = `T51_01`
- F = `F51_01`
- CV = `LC51_03CV`
- X = `LC51_03X`

A2:

- P1 = `P57_03`
- P2 = `P57_04`
- T1 = `T57_03`
- F = `FC57_03PV`
- CV = `FC57_03CV`
- X = `FC57_03X`

A3:

- P1 = `P74_00`
- P2 = `P74_01`
- T1 = `T74_00`
- F = `F74_00`
- CV = `LC74_20CV`
- X = `LC74_20X`

The official DAMADICS footnote states that for A2 f19 events the flow signal available in the data file is fault-free because the f19 fault was introduced only in the control loop. This limitation is accepted before execution; no compensating feature is added.

## Frozen adapter

For each of the 13 events, the adapter may only:

1. parse the selected daily source file numerically;
2. preserve original integer seconds-from-midnight timestamps;
3. extract exactly `[event_start - 300, event_start + 300)`;
4. select the 18 official local columns above;
5. rename them deterministically in canonical order to:
   - `A1_sig01` ... `A1_sig06`
   - `A2_sig01` ... `A2_sig06`
   - `A3_sig01` ... `A3_sig06`;
6. preserve missing values as missing values;
7. serialize losslessly to the frozen compiler's Parquet input contract.

No interpolation, imputation, resampling, smoothing, normalization, clipping, detrending, residual construction, domain-specific feature engineering, unit conversion or target-conditioned transformation is allowed.

No signal may receive suffix `cpu`, `mem`, `socket`, or `diskio`; all 18 signals therefore remain on the compiler's generic symptom path.

Because the frozen ERC-1 compiler discovers candidate files using the legacy opaque `E1-*.json` contract, ERC-2AR opaque IDs retain the `E1-` prefix. That prefix carries no target information.

## Frozen compiler

`experiments/erc1/compiler.py` must remain byte-identical with SHA-256:

`2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d`

No compiler constant, formula, weight, tie-break, packet rule or time window may change.

In particular:

- pre-window = 300 seconds
- post-window = 300 seconds
- minimum finite points per side = 20
- robust median/P10/P90 shift score unchanged
- denominator/noise floors unchanged
- score cap = 30
- entity aggregation unchanged
- packet capacity = 16

## Candidate/scorer isolation

Candidate-visible metadata contains only:

- opaque event ID;
- event start second;
- source raw-file SHA-256;
- staged Parquet SHA-256.

Candidate-visible signal columns reveal only candidate entity identity `A1`, `A2`, `A3` and generic signal ordinal.

The candidate side must not contain:

- event item number;
- calendar date;
- source filename;
- fault code;
- fault description;
- true actuator label;
- original DAMADICS variable name.

Scorer-only mapping contains those fields and is opened only after live and replay prediction seals exist.

## Transparent simplicity baseline

`LARGEST_SINGLE_SHIFT` is frozen before telemetry performance.

For each candidate actuator, take the maximum individual normalized feature score among its six adapted signals using the exact frozen `score_feature` calculation. Rank actuators by that maximum, lexical tie-break.

The baseline receives no multi-signal corroboration.

## One-shot outcome criteria

Scientific n = 13.

Every integrity-valid run is terminal.

### `ERC2AR_STRICT_TRANSFER_PASS`

Requires all of:

- source/data-binding qualification PASS;
- compiler SHA PASS;
- exactly 13 candidate/scorer events matching the frozen IDs;
- live/replay prediction bytes identical;
- provenance PASS;
- packet capacity PASS;
- ERC top-1 = **13/13**;
- ERC top-3 = **13/13**;
- A1 = 6/6 top-1;
- A2 = 5/5 top-1;
- A3 = 2/2 top-1;
- `LARGEST_SINGLE_SHIFT` top-1 <= **11/13**.

The <=11 baseline gate preserves the predecessor protocol's requirement that corroboration earn at least a two-event advantage rather than receiving credit for a statistical tie.

### `ERC2AR_TRANSFER_PASS_SIMPLE_RULE_SUFFICIENT`

Requires all integrity conditions and ERC = 13/13, but `LARGEST_SINGLE_SHIFT` >= **12/13**.

Interpretation: cross-domain localization transfers, but ERC's multi-signal corroboration has not earned distinct mechanism credit over the simpler one-signal rule.

### `ERC2AR_TRANSFER_DISCREPANCY`

Any integrity-valid run with ERC top-1 < **13/13**.

`12/13` is a discrepancy. No threshold is relaxed after execution.

### Integrity-invalid / pre-prediction states

Source ambiguity, bad archive inventory, daily-file shape failure, adapter mismatch, compiler-hash mismatch, opacity/provenance violation, or replay mismatch are not scientific transfer results.

## No same-set rescue

Once the first live ERC prediction seal exists:

- the 13-event result is evidence;
- the adapter is frozen;
- the compiler remains frozen;
- no event may be dropped;
- no new signal may be added;
- no weighting, normalization, window or threshold may be changed and rerun on these events.

If the result is a discrepancy, errors are analyzed rather than repaired on the same set.

## Nonclaims

A PASS would establish only a narrow result: the same deterministic witness compiler that reproduced RCAEval service localization transferred without mathematical modification to preregistered physical-actuator localization on 13 non-overlapping DAMADICS artificial-fault events.

It would not establish universal root-cause diagnosis, general causal inference, semantic understanding, consciousness, AGI or superiority over learned industrial FDI systems.

## State at preregistration

- successor branch created: YES
- official telemetry archives downloaded by ERC-2AR: **NO**
- telemetry values inspected for ERC-2AR: **NO**
- adapter implemented: **NO**
- source archive hashes known: **NO**
- live predictions: **0**
- scorer opened after prediction: **NO**
- model/LLM calls: **0**
