# ERC-3B — PROTECT-90 time-base calibration + fresh onset-precedence transfer

Status: **PREREGISTERED / PRE-CALIBRATION / PRE-SCIENCE**

## Predecessor boundary

ERC-3A is terminal.

Authorized ERC-3A attempt 2 at head `b0bdbaf0bbb86f8f8eadda3286ddc9925a862e04` stopped during first-waveform staging with:

`ValueError: time axis is not the frozen 6.4 kHz 0..6399/6400 grid`

ERC-3A produced:

- scientific predictions: 0
- replay predictions: 0
- scorer access: none
- scientific score: none

ERC-3B does **not** rerun, repair, rescore, or reinterpret ERC-3A. The 64 ERC-3A scientific sample IDs are permanently excluded from ERC-3B science.

## Research question

After independently qualifying the real PROTECT-90 timestamp encoding on non-scientific calibration episodes, does preregistered two-ended disturbance-onset precedence localize faulted line sections on a completely fresh, balanced 64-episode cohort more reliably than post-fault magnitude alone or single-ended onset?

## Why a successor is allowed

PROTECT-90 publicly specifies 6,400 synchronized samples per episode, approximately 6.4 kHz sampling, one `time_s` column, and 48 self-describing waveform channels. ERC-3A failed because it additionally assumed one exact floating-point representation of that time axis before observing any real payload.

ERC-3B treats time-base interpretation as an independently qualified measurement-layer contract rather than silently changing it after scientific execution.

## Dataset binding

Primary dataset: PROTECT-90.

- Zenodo record: `10.5281/zenodo.21109169`
- companion repository commit: `d07e574eebbee62fe6b2b7eb84df437dd3714011`
- labels MD5: `5f015330f77ed53b76bd5db26e83c48d`
- waveform archive MD5: `7cf176f169299b825ba6a6be102edca8`
- total episodes: 9,022
- waveform shape contract: 6,400 rows × 49 named columns
- signal channels: 48 = eight relay locations × three phase currents + three phase voltages

No scientific waveform may be opened until metadata selection, remote-index qualification, and time-base calibration rules are frozen.

## Identity firewall

ERC-3B retains the ERC-3A three-layer identity separation:

1. **ACQUISITION_MAP** — `opaque_id -> sample_id -> t_evnt_start`, acquisition layer only.
2. **PRODUCER_MANIFEST** — opaque identity, event alignment, waveform/hash binding, channel schema; never `sample_id`, `fault_target`, `sc_type`, `sc_location`, or scorer-derived fields.
3. **SCORER_MAP** — `opaque_id -> truth`, inaccessible to locator until live and replay prediction seals exist and match exactly.

Producer-visible JSON is mechanically scanned for forbidden truth-linkage fields.

## Permanent exclusions

Before selecting ERC-3B cases, construct the exclusion set from the committed ERC-3A acquisition map.

The exclusion set includes all 64 ERC-3A scientific `sample_id` values.

No excluded sample may appear in calibration or ERC-3B science.

## Calibration-only cohort

Calibration n = 8.

Calibration cases are selected without using fault target, fault type, fault location, resistance, or any performance-relevant label.

From all non-excluded rows with non-null `sample_id` and `t_evnt_start`:

1. compute SHA-256 of `ERC3B-TIMEBASE-CAL-v1|<sample_id>`;
2. sort ascending by digest, then numerically by `sample_id`;
3. take the first eight rows.

Calibration IDs are then added to the permanent ERC-3B science exclusion set.

### Calibration access boundary

For the eight calibration payloads, code may inspect only:

- payload identity/hash;
- object type;
- DataFrame shape;
- column names and uniqueness;
- the `time_s` vector;
- derived differences between adjacent `time_s` values.

Calibration code MUST NOT:

- read or summarize current/voltage numeric values;
- compute RMS, onset, magnitude, fault score, line ranking, or prediction;
- access scorer truth fields beyond the sample identity needed for acquisition;
- use fault target/type/location/resistance to choose or interpret calibration cases.

## Frozen time-base qualification rule

Each calibration episode must satisfy all of the following:

1. DataFrame shape exactly `(6400, 49)`.
2. Exact required set of 49 column names: `time_s` plus the frozen 48 waveform channels. Source column order is not meaningful and may differ.
3. `time_s` has exactly 6,400 finite values.
4. `time_s` is strictly increasing.
5. First time is within `[-1e-9, +1e-9]` seconds.
6. Median adjacent sample interval is positive.
7. Effective sample rate `1 / median(diff(time_s))` is in `[6390, 6410]` Hz.
8. Maximum absolute deviation of adjacent intervals from their median is <= `1e-9` seconds.
9. All eight calibration time vectors are byte-identical when canonicalized to little-endian IEEE-754 float64 bytes.

If any condition fails, terminal status is:

`ERC3B_TIMEBASE_QUALIFICATION_FAIL`

No scientific waveform may then be opened.

### Frozen event alignment

If calibration passes, scientific event alignment uses the actual qualified `time_s` vector:

`event_sample_index = first index i such that time_s[i] >= t_evnt_start`

This is equivalent to `numpy.searchsorted(time_s, t_evnt_start, side="left")`.

The scientific producer receives the resulting event sample index, not the raw acquisition identity.

The time vector itself is not a scoring feature.

## Fresh scientific cohort

Scientific n = 64.

After removing:

- all 64 ERC-3A scientific IDs; and
- the eight ERC-3B calibration IDs,

select four rows from each `(fault_target × sc_type)` stratum using:

1. require non-null `sample_id`, `fault_target`, `sc_type`, `t_evnt_start`;
2. compute SHA-256 of `ERC3B-PROTECT90-SCI-v1|<sample_id>`;
3. sort ascending by digest, then numerically by `sample_id`;
4. take the first four rows in each stratum.

Expected:

- 4 fault targets × 4 fault types = 16 strata;
- 4 per stratum;
- 64 total scientific episodes;
- zero overlap with ERC-3A science;
- zero overlap with ERC-3B calibration.

If the balanced selection cannot be formed exactly, ERC-3B terminates pre-science.

## Scientific method — unchanged onset hypothesis

Only phase-current channels are used by the primary locator.

For every relay and phase current:

1. causal one-cycle RMS: 128 samples;
2. pre-event robust baseline from the 640 complete RMS samples immediately before the qualified event sample index;
3. robust center = median;
4. robust scale = max(`1.4826*MAD`, `IQR/1.349`, `0.01*abs(center)`, `1e-12`);
5. standardized disturbance = absolute RMS deviation / robust scale;
6. onset threshold = 5.0 robust sigma;
7. persistence = 32 consecutive samples;
8. post-event search horizon = 640 samples.

For a line with sending and receiving relays:

- **primary two-ended onset** = later of the two endpoint onsets;
- if either endpoint has no persistent onset, the line has no primary onset;
- rank lines by earliest primary onset;
- frozen tie-break: larger preregistered local peak support, then lexical line ID.

No learning, fitted weights, fault-label access, or per-case tuning.

## Registered controls

### Magnitude-only

For each line, sum the maximum standardized post-event current disturbance at its two endpoints. Rank descending.

### Single-ended onset

Use only the sending-end onset. Rank by earliest persistent onset with the already registered deterministic tie-break.

### Topology-only negative control

May use only the frozen line list/topology; no waveform values and no truth.

## Frozen scientific gates

Primary quality gates:

- primary top-1 >= 60/64;
- every faulted line >= 14/16 primary top-1;
- deterministic live/replay byte identity = 1.00;
- all 64 payload and producer bindings valid;
- producer truth leakage = 0.

Mechanism-credit gates:

- primary margin over magnitude-only >= 8 cases;
- primary margin over single-ended onset >= 4 cases.

Terminal interpretation:

- quality gates + both mechanism margins PASS -> `ERC3B_COORDINATED_ONSET_PASS`
- quality gates PASS but either mechanism margin fails -> `ERC3B_ONSET_SIGNAL_SIMPLE_RULE_SUFFICIENT`
- any integrity-valid primary quality gate fails -> `ERC3B_TRANSFER_DISCREPANCY`
- broken isolation, replay, payload, freeze, or scorer order -> `ERC3B_INTEGRITY_INVALID`

## Same-set rule

Once any ERC-3B scientific live prediction is emitted:

- no threshold change;
- no persistence change;
- no window change;
- no tie-break change;
- no selected-case replacement;
- no feature addition;
- no same-set rerun presented as fresh evidence.

Post-result diagnostics may inspect failures, but any new hypothesis requires a separately preregistered successor on a new scientific set.

## Runtime binding

Pre-live qualification and live execution must bind exact runtime versions before authorization. Runtime changes after a freeze require requalification before scientific payload access.

## Claim boundary

A PASS would support only the narrow claim that preregistered disturbance-onset ordering can transfer to a foreign power-system fault-localization benchmark under the stated observability assumptions.

It would not establish:

- general causal identification;
- field-ready power-system protection;
- certified relay performance;
- general machine reasoning;
- semantic understanding;
- consciousness or AGI;
- validity outside the tested topology/domain.

A FAIL remains a useful boundary result.