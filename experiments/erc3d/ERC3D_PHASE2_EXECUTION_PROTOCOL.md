# ERC-3D Phase 2 — Frozen Scientific Execution Contract

Status: PRE-LIVE. No ERC-3D science waveform has been opened and no scientific prediction exists.

This file is authoritative for Phase 2 unless a defect is found **before** any ERC-3D science waveform is opened. Once the first science waveform is opened, this scientific set may not be repaired, retuned, reselected, or rerun after any code/parameter change.

## 1. Bound Phase-1 qualification

Phase 1 terminal record: `experiments/erc3d/ERC3D_PHASE1_TERMINAL.json`.

Required bindings:

- qualified Phase-1 implementation head: `347380a0b5bcf7a39862dd47b49e3c215412e0b8`
- reserved science-64 ID SHA-256: `12d842682aa93f54a867e1194ad6e0c268ddebb04e076a7da8a4dc10c363fe9`
- common released raw `time_s` vector SHA-256: `5fbf69daee8e11889b46cd483925a6b6b3dbbaf17ca17bd45254420f0fe0ee1f`
- common released integer-microsecond vector SHA-256: `82851c788ae37d3905a9f6f8d8cb732ddf83fd75b35242060999e6a7b151f5d2`
- Phase-1 contract self-hash: `c4e19b2add054d524e17835bd5a696b3c3bbc991b70169d643ac859971067e65`
- Phase-1 receipt self-hash: `60c40c6be05f63cfeb8fedf55ccc174ad8e9f5a71c369e33f6784f55ccda801e`

The 64 reserved science cases MUST NOT be reselected.

## 2. Scientific time coordinate

The qualified release representation is a whole-microsecond encoding of the published 6.4 kHz endpoint grid.

The scientific coordinate is therefore fixed to:

```python
nominal_time = (np.arange(6400, dtype=np.float64) + 1.0) / 6400.0
event_index = int(np.searchsorted(nominal_time, t_evnt_start, side="left"))
```

Equivalent integer mathematics is allowed only if regression-tested against this expression for the full valid event-time range.

Important: this is an endpoint grid. For a fault exactly at 0.200000 s the first sample at/after the event is array index 1279, not 1280. Do not reuse ERC-3A's old zero-origin `ceil(t*6400)` index unchanged.

Forbidden:

- interpolation;
- resampling;
- fitted clock offset;
- fitted sample rate;
- per-case time correction;
- use of released rounded `time_s` to rank or score onset;
- any threshold search using the 64 science cases.

## 3. Per-science-waveform compatibility gate

Before reading V/I signal columns for a science case, staging must validate its DataFrame and `time_s` only.

Required for every one of the 64 cases:

- pandas DataFrame shape exactly `(6400, 49)`;
- exact frozen set of `time_s + 48` channel names; source column order may differ and must be deterministically reordered;
- finite and strictly increasing `time_s`;
- raw float64 `time_s` SHA-256 exactly `5fbf69daee8e11889b46cd483925a6b6b3dbbaf17ca17bd45254420f0fe0ee1f`;
- integer-microsecond vector SHA-256 exactly `82851c788ae37d3905a9f6f8d8cb732ddf83fd75b35242060999e6a7b151f5d2`.

All 64 science payloads must complete this compatibility gate before prediction #1 is emitted. If any fails, terminal state is `ERC3D_SCIENCE_TIMEBASE_INTEGRITY_INVALID`; no scientific score is permitted.

## 4. Producer/scorer isolation

Producer-visible material may contain only:

- opaque ID;
- `t_evnt_start`;
- waveform payload SHA-256;
- frozen channel schema;
- waveform values.

Producer-visible material MUST NOT contain raw `sample_id`, `fault_target`, `sc_type`, `sc_location`, active-line truth, scorer truth, or any label-derived field.

The acquisition mapping may privately bind opaque ID -> sample ID solely for archive access. The scorer mapping remains inaccessible until live and replay prediction seals both exist and are byte-identical.

Add a recursive committed-artifact and runtime-manifest leakage scan for the forbidden fields.

## 5. Primary locator — mechanism frozen

Reuse the ERC-3A onset mechanism without parameter changes. Prefer importing its already-qualified pure primitives rather than copying/reimplementing them.

Frozen constants:

- causal RMS window: 128 samples;
- baseline window: 640 samples;
- post-event window: 640 samples;
- robust onset threshold: 5.0 sigma;
- persistence: 32 samples;
- tie-peak window: 128 samples;
- primary line onset: later onset of the two line endpoints.

The **only authorized timing-semantic difference** from ERC-3A is Section 2's endpoint-grid event index.

The primary method must still use three-phase current channels at both endpoints and the same robust center/scale, persistent-onset, line-ranking, and deterministic tie rules as ERC-3A.

## 6. Registered controls

Run on the exact same staged inputs:

1. `single_ended` — sending-end onset only, otherwise unchanged;
2. `magnitude_only` — strongest standardized post-event magnitude, otherwise unchanged.

No new control may be added after seeing scientific predictions. Additional diagnostics may be computed only after terminal scoring and may not change the registered verdict.

## 7. Synthetic qualification before authorization

Before real science waveform access, Phase 2 must pass a synthetic-only qualification suite that proves at minimum:

- endpoint-grid indexing, including exact endpoints and between-sample times;
- one-sample distinction from ERC-3A zero-origin indexing where expected;
- causal RMS unchanged;
- robust center/scale unchanged;
- 5-sigma/32-sample persistence unchanged;
- later-of-two-endpoints primary rule unchanged;
- single-ended and magnitude-only controls unchanged;
- deterministic line tie ordering;
- producer forbidden-field rejection;
- exact-schema order-insensitivity plus missing/extra/duplicate-name rejection;
- science time-vector compatibility hash gate;
- deterministic canonical prediction serialization;
- live/replay seal equality;
- scorer refuses mismatched/duplicate case sets;
- scorer cannot be invoked unless both prediction files exist and their seals match.

No test may use a selected ERC-3D science waveform or its signal values.

## 8. Freeze candidate

The pre-live freeze candidate must hash every executable and authority surface, including:

- this Phase-2 protocol;
- Phase-1 terminal record;
- Phase-1 preregistration;
- ERC-3D science acquisition map/public selection/producer manifest/index;
- endpoint-time locator/wrapper;
- stage/acquisition code;
- scorer;
- prediction sealing/replay code;
- producer-boundary scanner;
- pre-live tests;
- pre-live workflow;
- live workflow;
- exact runtime declaration.

Required hosted runtime unless the freeze explicitly stops before authorization:

- Python 3.11.16
- NumPy 2.2.6
- pandas 2.3.2

The freeze candidate must report zero ERC-3D science waveform payloads opened and zero scientific predictions.

## 9. Authorization and irreversible boundary

A separate authorization commit may change only `experiments/erc3d/ERC3D_PHASE2_FREEZE.json` over an exact green qualified parent head.

Before first payload access the live workflow must verify:

- exact parent head;
- freeze-file-only authorization commit;
- every frozen source hash;
- exact runtime;
- exact reserved science-64 identity hash;
- exact archive/index binding.

If the run fails before the first science waveform is opened due only to external infrastructure/transport, a byte-identical freeze may be reauthorized with the failure preserved. Once the first ERC-3D science waveform is opened, no code/parameter/selection repair is permitted for this set.

## 10. Live execution order

Exact order:

1. verify authorization and freeze;
2. verify runtime and bindings;
3. acquire/stage all 64 science waveforms;
4. validate all 64 time vectors against Section 3;
5. seal staged producer manifests;
6. emit all 64 LIVE predictions;
7. seal LIVE predictions;
8. independently rerun all 64 from the sealed staged producer inputs;
9. seal REPLAY predictions;
10. require byte-identical LIVE/REPLAY serialization;
11. only then open/reconstruct scorer truth;
12. score once;
13. preserve all evidence regardless of PASS/FAIL.

No per-case retry after prediction generation. No same-set rescue.

## 11. Frozen scientific gates

Exactly 64 cases: 16 truth cases for each of the four faulted line sections.

Primary quality gates:

- primary top-1 >= 60/64;
- primary top-1 >= 14/16 on every faulted line.

Mechanism-credit margins:

- primary - magnitude-only >= 8 cases;
- primary - single-ended >= 4 cases.

Terminal scientific interpretations:

- `ERC3D_COORDINATED_ONSET_PASS` — both quality gates and both mechanism margins PASS;
- `ERC3D_ONSET_SIGNAL_SIMPLE_RULE_SUFFICIENT` — both quality gates PASS but at least one mechanism margin FAILS;
- `ERC3D_TRANSFER_DISCREPANCY` — either primary quality gate FAILS.

Integrity failures are separate from scientific failures and must never be converted into one of the three scientific interpretations.

## 12. Interpretation boundary

A coordinated PASS would support only this narrow statement: on this fresh PROTECT-90 cohort, two-ended persistent current-onset ordering localized the faulted line under the frozen measurement contract substantially better than the registered simpler controls.

It would not establish general causal discovery, universal protection logic, AI cognition/memory, optimal relay design, deployment safety, or transfer beyond the tested topology.
