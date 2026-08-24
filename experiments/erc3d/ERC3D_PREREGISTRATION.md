# ERC-3D Preregistration — Quantized-Time Representation + Fresh PROTECT-90 Transfer

## Status

Protocol-only successor to terminal ERC-3C. Commit this document before any ERC-3D payload access.

ERC-3D does not repair, rerun, rescore, or reinterpret ERC-3A/B/C. Their terminal records remain authoritative.

## Motivation

ERC-3C calibration observed the same timing diagnostics in all eight fresh calibration members:

- first stored time: `0.000156 s`
- last stored time: `1.000000 s`
- median stored increment: approximately `0.000156 s`
- maximum increment deviation: approximately `1 microsecond`
- maximum residual against a 6.4 kHz nominal grid: approximately `0.5 microsecond`

These observations are consistent with, but do not prove, a fixed 6.4 kHz endpoint grid stored after quantization to whole microseconds.

The public PROTECT-90 specification states 6,400 samples per one-second episode and a 6.4 kHz sampling rate. ERC-3D therefore tests a fresh, falsifiable representation hypothesis before any scientific waveform is opened.

## Representation hypothesis

For sample indices `i = 0..6399`, define the physical endpoint grid:

`nominal_i = (i + 1) / 6400` seconds.

ERC-3D hypothesizes that the released `time_s` values are a microsecond-quantized representation of this physical endpoint grid.

This is a measurement-format claim only. It is not a fault-localization result.

## Strong fresh-set boundary

Permanently exclude every sample ID selected by any earlier PROTECT-90 unit, including unopened reserved science cases:

1. ERC-3A science-64;
2. ERC-3B calibration-8;
3. ERC-3B reserved science-64;
4. ERC-3C calibration-8;
5. ERC-3C reserved science-64.

Expected exclusion union cardinality: 208, subject to an explicit equality check. Any overlap or cardinality mismatch is terminal pre-data failure.

ERC-3D selects:

- calibration: 8 new episodes using a new fault-label-blind SHA-256 salt `ERC-3D-CAL-v1`;
- science: 64 new episodes using salt `ERC-3D-SCI-v1`, balanced 4 cases from each of the 16 `(fault_target × sc_type)` strata.

Calibration and science must be mutually disjoint and disjoint from the permanent exclusion union.

## Identity boundary

Maintain three physically distinct artifacts:

1. `ACQUISITION_MAP`: opaque ID -> sample ID -> required member binding and `t_evnt_start`;
2. `PRODUCER_MANIFEST`: opaque ID, role, payload hash/binding, public channel schema; MUST NOT contain `sample_id`, `fault_target`, `sc_type`, `sc_location`, or scorer fields;
3. `SCORER_MAP`: opaque ID -> truth; inaccessible to calibration, locator, controls, live/replay prediction generation.

Producer-visible JSON leakage regression is mandatory.

## Phase 1 — calibration only

Phase 1 may open exactly the eight fresh calibration waveform members and no science member.

Calibration may inspect only:

- Python object type;
- DataFrame shape;
- column names;
- `time_s` values.

It must never index or compute a statistic from any current or voltage signal column.

Each of the eight calibration cases must satisfy all of the following:

1. pandas DataFrame shape exactly `(6400, 49)`;
2. exact frozen set `time_s + 48 published channels`; source column order may differ;
3. `time_s` finite and strictly increasing;
4. raw `time_s` values lie on an integer-microsecond representation grid:
   `max(abs(time_s - rint(time_s * 1e6) / 1e6)) <= 5e-13 s`;
5. physical endpoint-grid consistency:
   `max(abs(time_s - ((arange(6400)+1)/6400))) <= 0.500001e-6 s`;
6. last stored timestamp within `5e-13 s` of `1.0 s`;
7. all eight raw time vectors have exactly one canonical little-endian float64 SHA-256 value;
8. all eight microsecond-quantized integer vectors have exactly one canonical SHA-256 value.

No fitted rate, learned offset, interpolation, resampling, warping, per-case correction, or threshold search is permitted.

### Phase-1 terminal states

- `ERC3D_QUANTIZED_TIME_QUALIFICATION_PASS`
- `ERC3D_QUANTIZED_TIME_QUALIFICATION_FAIL`

A PASS requires all eight calibration cases to satisfy every condition. A FAIL terminates ERC-3D before science access. There is no ERC-3D calibration repair or rerun.

Required boundary counters in either terminal record:

- calibration waveforms opened = 8;
- scientific waveforms opened = 0;
- scientific signal columns read = 0;
- scientific predictions = 0;
- scorer opened = false.

If Phase 1 PASSes, STOP. Scientific execution requires a separate exact-head pre-live qualification and authorization.

## Scientific coordinate after a Phase-1 PASS

The scientific coordinate is the unquantized physical endpoint grid:

`nominal_time = (arange(6400) + 1) / 6400`

Fault-event alignment is frozen as:

`event_index = searchsorted(nominal_time, t_evnt_start, side='left')`

The raw rounded `time_s` column is not used by the locator after schema validation.

No interpolation or resampling is performed.

## Scientific mechanism — unchanged hypothesis

ERC-3D preserves the ERC-3A onset-precedence mechanism and controls in substance:

- causal 128-sample one-cycle RMS;
- 640-sample pre-event and 640-sample post-event windows;
- robust pre-event baseline;
- 5.0 robust-sigma onset threshold;
- 32-sample persistence;
- primary line onset = later onset of the two line endpoints;
- earliest primary onset ranks fault target;
- magnitude-only control;
- single-ended onset control.

No learned weights.

## Frozen scientific gates

For the fresh 64 scientific cases:

- primary top-1 >= 60/64;
- every faulted line >= 14/16;
- coordinated mechanism credit additionally requires >=8-case top-1 margin over magnitude-only control;
- coordinated mechanism credit additionally requires >=4-case top-1 margin over single-ended onset control.

If a simpler control ties or nearly matches the primary method, simplicity gets the mechanism credit.

No same-set rescue, retuning, threshold alteration, reselection, or method repair after live predictions exist.

## Interpretation boundary

A PASS would support only a narrow claim that onset ordering transfers to this fresh PROTECT-90 cohort under a documented fixed-rate sample coordinate. It would not establish general causal identification, universal protection logic, general memory, semantic understanding, AGI, consciousness, or a product claim.

A Phase-1 FAIL retires PROTECT-90 from this onset-precedence line unless a future experiment uses an independently justified measurement contract from an external authoritative source rather than another post-hoc fit to these payloads.
