# ERC-3C — PROTECT-90 index-time calibration + fresh onset transfer

Status: **PREREGISTERED / PRE-PAYLOAD**

This unit is a fresh successor to terminal ERC-3B. It does not repair, rerun, score, or reinterpret ERC-3A or ERC-3B.

## 1. Predecessor boundary

ERC-3A terminated pre-prediction after two authorized attempts. Attempt 2 stopped because the first selected waveform failed an exact stored-time-origin contract. Scientific predictions remained 0 and the scorer was not opened.

ERC-3B then separated time-base calibration from science. Its Phase-1 calibration opened exactly 8 calibration-only members and terminated:

`ERC3B_TIMEBASE_QUALIFICATION_FAIL`

Frozen ERC-3B facts:

- head: `b8f506296df1304c4b5790bc4f3df5297cbdcad8`
- old ERC-3A science-64 ID hash: `aef9418b6ee352f0c2ab96ac6ecb7e097aa834662a646453495905a1c6dcf6db`
- ERC-3B calibration-8 hash: `eb22af50794fd52b5dca50bfea97aeec733ef2b829c870299b261d2012f0cec1`
- ERC-3B reserved fresh science-64 hash: `2c7709b66306bd4f3c2b9bf5c7e0ee1aea0177a360ab29e4e1c12d0a7be8778e`
- calibration waveforms opened: 8
- ERC-3B science waveforms opened: 0
- scientific predictions: 0
- scorer opened: false
- timebase contract SHA-256: `5b5425669d263cc52f13e2555d056d27e99c837ee05435ba26687231b25f8054`
- calibration receipt SHA-256: `3a93f8358a5e77be9785ad4e304eeb83cefdc5ba2858b3aac1424516deee1be8`

All 8 calibration DataFrames were `(6400,49)` with the exact frozen 49-name schema, but all failed the preregistered `abs(time_s[0]) <= 1e-9` condition.

Important interpretation: ERC-3B's implementation raises immediately at that start-time check, before computing median interval, effective sampling rate, interval jitter, or a canonical time-vector hash. Therefore ERC-3B established a stored-origin mismatch only. It did **not** establish that the differential sample spacing is invalid or differs across episodes.

ERC-3B is terminal. Its 8 calibration IDs and its unopened 64 reserved science IDs are both excluded from ERC-3C in addition to the ERC-3A 64.

## 2. External representation contract

The public PROTECT-90 documentation states:

- 9,022 episodes;
- one `(6400,49)` pandas DataFrame per episode;
- 6.4 kHz sampling, 128 samples per 50 Hz cycle;
- a 1.0 s analysis window;
- 48 V/I channels plus `time_s`;
- `t_evnt_start` / `t_evnt_end` are event times in seconds;
- the documented `time_s` axis is 0 → 1 s in 1/6400 s steps.

Dataset release DOI: `10.5281/zenodo.18418330`.
Public documentation repository: `julianoelhaf/protect90-dataset`.

ERC-3C deliberately separates the scientifically meaningful **sample coordinate** from the release's stored clock origin.

## 3. Question

> If the released waveform spacing is demonstrably affine-equivalent to the documented 6.4 kHz sample grid, can the preregistered onset-precedence locator identify the faulted line on a completely fresh 64-case PROTECT-90 cohort?

This is a measurement-contract successor, not same-set rescue.

## 4. Permanent exclusions

Before selecting any ERC-3C case, construct a union of all sample IDs belonging to:

1. ERC-3A scientific 64;
2. ERC-3B calibration 8;
3. ERC-3B reserved science 64.

The selection code must assert that every ERC-3C calibration/science sample ID is absent from this union.

The union's raw sample IDs may exist only in acquisition/scorer-private artifacts. Producer-visible artifacts remain opaque.

## 5. Fresh selection

### 5.1 Calibration cohort

Select exactly 8 fresh calibration-only episodes from the exclusion-filtered metadata using a new disclosed SHA-256 ordering salt:

`ERC-3C-CALIBRATION-v1`

Calibration selection is fault-label-blind after eligibility filtering. Calibration cases are used only for schema and `time_s` qualification.

### 5.2 Scientific cohort

Select a completely fresh 64-case scientific cohort with a different disclosed salt:

`ERC-3C-SCIENCE-v1`

Maintain the ERC-3A 4×4 stratification:

- four `fault_target` line sections;
- four `sc_type` categories;
- exactly 4 cases per `(fault_target, sc_type)` stratum;
- total n = 64.

The science cohort must be disjoint from all permanent exclusions and the 8 ERC-3C calibration cases.

Selection is frozen before any ERC-3C calibration waveform is opened.

## 6. Identity firewall

Three layers are required:

### Acquisition map

May contain:

`opaque_id -> sample_id -> t_evnt_start -> archive member binding`

It may be used only by acquisition/staging code.

### Producer manifest

May contain only:

- `opaque_id`;
- event time needed for alignment;
- payload/hash binding;
- frozen channel schema;
- frozen sample-coordinate contract.

It must not contain `sample_id`, `fault_target`, `sc_type`, `sc_location`, phase labels, or scorer-derived fields.

### Scorer map

May contain opaque ID and truth fields. It must remain unavailable to the locator until live and replay prediction seals both exist and match.

Regression tests must scan every committed producer-visible JSON artifact and reject forbidden identity/truth fields.

## 7. ERC-3C calibration contract

Calibration may inspect only:

- payload object type;
- DataFrame shape;
- column names;
- `time_s` values.

It may not read any current or voltage signal column.

Each of the 8 fresh calibration cases must satisfy all of the following:

1. pandas DataFrame;
2. exact `(6400,49)` shape;
3. exact frozen 49-name set, source order irrelevant;
4. finite `time_s` values;
5. strictly increasing `time_s`;
6. `dt = diff(time_s)` has positive finite median;
7. `abs(median(dt) - 1/6400) <= 1e-9 s`;
8. `max(abs(dt - median(dt))) <= 1e-9 s`.

**The raw value of `time_s[0]` is recorded but is not a gate.**

For each case define:

`relative_time[k] = time_s[k] - time_s[0]`

and the documented nominal coordinate:

`nominal_time[k] = k / 6400`, for `k = 0..6399`.

Require:

`max(abs(relative_time - nominal_time)) <= 1e-7 s`.

This tolerance is predeclared before any ERC-3C payload access. It is approximately 0.00064 of one sample interval and cannot move an event boundary by a sample.

Calibration PASS additionally requires all 8 cases to pass individually. Raw origin values are summarized for audit but are not normalized by a learned per-case parameter beyond subtracting the observed coordinate origin.

Terminal calibration states:

- `ERC3C_INDEX_TIME_QUALIFICATION_PASS`
- `ERC3C_INDEX_TIME_QUALIFICATION_FAIL`

If calibration FAILS: stop. Open zero scientific waveforms. Produce zero scientific predictions. Do not create ERC-3C-R on these same calibration/science IDs.

## 8. Frozen scientific event coordinate

If and only if calibration passes, scientific event alignment ignores the arbitrary stored origin and uses the documented sample-index coordinate:

`nominal_time = arange(6400) / 6400`

`event_index = searchsorted(nominal_time, t_evnt_start, side='left')`

Equivalently, this selects the first documented sample coordinate at or after fault inception.

The scientific payload's raw `time_s` must independently satisfy the same differential-grid checks used in calibration. If any science case fails those checks, the scientific execution is `INTEGRITY_INVALID`; it is not silently resampled or interpolated.

No interpolation, resampling, timestamp warping, fitted offset, fitted rate, or per-case timing correction is allowed.

## 9. Scientific locator — unchanged hypothesis

After event alignment, preserve the ERC-3A mechanism and controls:

- 48 raw synchronized channels;
- current channels used for onset locator as preregistered;
- causal 128-sample one-cycle RMS;
- 640-sample pre-event baseline window;
- 640-sample post-event search window;
- robust 5.0-sigma onset threshold;
- 32-sample persistence;
- primary line onset = later of the two endpoint onset times;
- rank four line sections by earliest primary onset with deterministic frozen tie-break;
- magnitude-only control unchanged;
- single-ended onset control unchanged;
- no learned weights;
- no LLM/model calls.

## 10. Scientific gates

Science n = 64.

Primary quality gates:

- top-1 >= 60/64;
- every faulted line >= 14/16.

Mechanism-credit gates:

- primary >= magnitude-only + 8 cases;
- primary >= single-ended onset + 4 cases.

Terminal interpretation:

- quality gates PASS + both mechanism margins PASS -> `ERC3C_ONSET_PRECEDENCE_TRANSFER_PASS`
- quality gates PASS but a simpler control is within its frozen margin -> `ERC3C_ONSET_SIGNAL_SIMPLE_RULE_SUFFICIENT`
- quality gates FAIL -> `ERC3C_TRANSFER_DISCREPANCY`
- any provenance/identity/runtime/time-grid/replay/scorer-order violation -> `ERC3C_INTEGRITY_INVALID`

A simple-control win/tie is evidence against coordinated-onset-specific credit, not a reason to tune.

## 11. Replay and scoring order

1. exact runtime/freeze verification;
2. acquire and stage exactly 64 science payloads under opaque identities;
3. validate schema + differential time-grid contract for every science case;
4. emit live predictions;
5. emit independent deterministic replay predictions;
6. require byte-identical live/replay files;
7. seal prediction SHA-256;
8. only then reconstruct/open scorer map;
9. score primary and registered controls;
10. seal terminal receipt/evidence artifact.

## 12. No-rescue rule

Once the first ERC-3C live prediction file exists, there is no same-set repair, threshold change, event-coordinate change, signal-set change, tie-break change, exclusion change, or rerun for scientific improvement.

If a pre-prediction mechanical failure occurs after waveform access, any successor must use fresh scientific IDs again unless the failure is a purely external transport outage that opened zero payload bytes.

## 13. Current boundary

At creation of this protocol:

- ERC-3C calibration payloads opened: 0;
- ERC-3C science payloads opened: 0;
- ERC-3C scientific predictions: 0;
- scorer opened: false;
- no ERC-3C selection artifacts yet exist;
- no ERC-3C live authorization exists.

The next allowed work is Phase 1 only: fresh metadata selection, exclusion proof, identity split, remote-member binding, and 8-case `time_s`/schema calibration. Scientific waveform access remains prohibited until that exact head is reviewed and calibration is green.
