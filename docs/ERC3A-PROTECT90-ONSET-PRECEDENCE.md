# ERC-3A — PROTECT-90 onset-precedence transfer

Status: PREREGISTERED / PRE-WAVEFORM

## Research question

Does simple disturbance-onset precedence localize a faulted power-system line more reliably than post-fault magnitude alone when applied to a physically distinct, synchronized protection dataset?

This unit is a fresh-domain successor to terminal ERC-2AR. ERC-2AR reached 12/13 on DAMADICS and missed the same item as a largest-single-shift control. Post-hoc inspection showed that the miss was dominated by a strong coherent control response in the wrong actuator. ERC-3A therefore tests the cheaper hypothesis first: source-adjacent measurements should change before propagated responses.

ERC-3A does **not** reuse or modify the ERC-1B compiler. It is a new mechanism test, not a rescue of the DAMADICS 13-case set.

## Data binding

Primary dataset: PROTECT-90.

- latest data-bearing Zenodo record at preregistration: `10.5281/zenodo.21109169`
- companion repository commit: `d07e574eebbee62fe6b2b7eb84df437dd3714011`
- published labels file MD5: `5f015330f77ed53b76bd5db26e83c48d`
- published waveform archive MD5: `7cf176f169299b825ba6a6be102edca8`
- 9,022 episodes
- 6,400 samples/episode
- 6.4 kHz sampling
- 48 waveform channels = 8 relay locations × (Iabc + Vabc)
- truth fields used only for selection/scoring: `fault_target`, `sc_type`
- event-time field exposed to producer: `t_evnt_start`

No waveform member may be opened before the metadata-only selection record is frozen.

## Fixed first-shot sample

Scientific n = 64.

The labels CSV is used only to construct a balanced scorer map before waveform access.

For every `(fault_target, sc_type)` stratum:

1. require the row to have a non-null `sample_id`, `fault_target`, `sc_type`, and `t_evnt_start`;
2. compute SHA-256 of `ERC3A-PROTECT90-v1|<sample_id>`;
3. sort ascending by that digest, then numerically by `sample_id`;
4. take the first four rows.

Expected strata: 4 faulted line sections × 4 fault types = 16.
Expected selected cases: 16 × 4 = 64.

If any stratum has fewer than four eligible rows, ERC-3A terminates pre-waveform.

The identity boundary is split into three mechanically separate artifacts:

1. `ACQUISITION_MAP`: `opaque_id -> sample_id -> t_evnt_start`. This is an acquisition-layer provenance artifact used only to resolve a selected archive member. It is never passed to the locator.
2. `PRODUCER_MANIFEST`: `opaque_id`, `t_evnt_start`, a ZIP central-directory waveform binding, and the frozen channel schema. It contains no `sample_id`, `fault_target`, `sc_type`, `sc_location`, or scorer-derived field. The pre-waveform binding is the SHA-256 of the archive identity and central-directory member tuple; the payload SHA-256 is populated only by the separately authorized acquisition step.
3. `SCORER_MAP`: `opaque_id -> truth`, held outside the locator process until live and replay prediction serializations have sealed identically.

The producer receives only opaque case id, selected waveform bytes, channel names, and `t_evnt_start`. A regression scans every producer-visible JSON artifact and fails on the forbidden fields `sample_id`, `fault_target`, `sc_type`, and `sc_location`.

The remote ZIP qualification reads only the archive tail, ZIP64 records when present, and the central directory using HTTP Range. It must prove exactly 9,022 waveform members and all 64 selected member bindings while reading zero selected payload bytes. Member acquisition is a separate layer from locator input construction.

## Primary method: two-ended onset precedence

Only phase-current channels are used by the primary locator. Voltage is not used in ERC-3A primary scoring because network-wide voltage disturbances may create broad simultaneous changes.

For each relay location and each phase current:

1. form a causal one-cycle RMS series using the current sample and previous 127 samples;
2. define the pre-event baseline from RMS samples whose full one-cycle window lies inside `[t_start - 0.100 s, t_start)`;
3. compute baseline center = median;
4. compute robust scale = max of:
   - `1.4826 * MAD`,
   - `IQR / 1.349`,
   - `0.01 * abs(median)`,
   - `1e-12`;
5. compute absolute standardized RMS deviation from the baseline center.

Relay onset is the first sample at or after `t_start` for which the maximum phase-current standardized deviation is at least **5.0** for **32 consecutive samples**. If no such run appears before `t_start + 0.100 s`, relay onset is infinity.

Each physical line section has two endpoint relay locations. Line onset is the **later** of its two endpoint onsets. This is a fixed both-ended-support rule: one changed endpoint is not enough.

Lines are ranked by:

1. earliest finite line onset;
2. if onset is tied to the same sample, larger sum of endpoint peak standardized phase-current deviation within the first 128 post-onset samples;
3. final deterministic tie-break: lexical line id.

No learned weights, fitted threshold, waveform normalization learned from other cases, or per-line calibration is allowed.

## Pre-waveform qualification terminal state

Before any of the 64 real episodes is executed, the repository may emit `ERC3A_PRELIVE_FREEZE_CANDIDATE_READY` only after:

- the 64-case identity split and producer-visible JSON scan pass;
- the remote archive range index proves 9,022 members and 64 selected bindings with zero payload reads;
- acquisition and locator code are separately compiled;
- the locator and all controls pass synthetic waveform fixtures only;
- live/replay prediction serialization is byte-identical on those synthetic fixtures; and
- the freeze candidate hashes all executable ERC-3A source, ERC-3A workflows, selection records, acquisition mapping rule, producer-manifest rule, and scorer.

This state records `waveform_members_opened = 0`, `scientific_predictions = 0`, and `same_set_rescue_authorized = false`. It does not authorize a scientific waveform run.

## Simplicity controls

### Control A — single-ended onset

For each line, use only the sending-end relay onset under the same RMS/threshold/persistence rule. Rank earliest first, then the same magnitude tie-break.

Purpose: if this matches the primary, two-ended coordination earns no mechanism credit.

### Control B — magnitude-only

Ignore onset ordering. Rank each line by the sum of the maximum standardized phase-current RMS deviation at its two endpoints during `[t_start, t_start + 0.100 s)`.

Purpose: test whether the line is simply the largest response.

### Control C — topology-only negative control

Use no waveform values. Among line sections marked active in metadata, rank lexically. If active-state metadata cannot be safely isolated from truth or if the relevant fields are ambiguous, this control is omitted and the omission is disclosed; it is not replaced post hoc.

## Scientific gates

The 64-case first shot has one terminal interpretation.

### `ERC3A_COORDINATED_ONSET_PASS`

All must hold:

- primary top-1 >= 60/64;
- each fault-target line >= 14/16;
- primary exceeds magnitude-only by at least 8 cases;
- primary exceeds single-ended onset by at least 4 cases;
- live/replay prediction seals match exactly;
- zero missing selected waveform members;
- zero scorer-label leakage before prediction seal.

### `ERC3A_ONSET_SIGNAL_SIMPLE_RULE_SUFFICIENT`

- primary top-1 >= 60/64;
- each line >= 14/16;
- but either simpler control is within the mechanism-credit margin above.

This means onset/local signal transferred, but coordinated two-ended logic earns no special credit.

### `ERC3A_TRANSFER_DISCREPANCY`

Any integrity-valid result failing the accuracy/per-line gates.

No same-64 rescue is authorized.

## Scaling rule

ERC-3A-SCALE is authorized only if the first shot reaches either PASS state above.

Scale sample: 512 cases selected from the remaining rows by the same stratum-balanced SHA ordering, 32 cases per `(fault_target, sc_type)` stratum, excluding all 64 first-shot sample ids.

No threshold, RMS window, persistence, tie-break, or channel choice may change between n=64 and n=512.

Scale success requires:

- primary >= 480/512;
- every fault-target line >= 120/128;
- the same simplicity-credit interpretation rule as the first shot.

If scale fails, preserve the failure. Do not tune and rerun the same 512.

## Deferred challenger: innovation residual

A command/response or causal-residual score is deliberately **not** part of ERC-3A. It is more complex and was motivated post hoc by the DAMADICS miss.

It may be tested only in a separately preregistered successor on waveform episodes not used by ERC-3A or ERC-3A-SCALE.

## Nonclaims

A PASS would not establish semantic understanding, consciousness, AGI, universal causal discovery, or general fault localization. It would support a narrower claim: in this benchmark family, simple time-of-disturbance precedence carries reproducible line-localization information beyond response magnitude, subject to the registered simplicity controls.
