# ERC-1B — Verified-Data-Binding Clean-Room Reproduction

## Status before execution

Preregistered successor to terminal ERC-1 data-binding failure.

ERC-1 never staged a case and never generated a prediction because its frozen Parquet revision (`92c773ab7bb79f525ec7d5dc53d96a74dbebce4d`) was a documentation snapshot that did not contain the required RE3 case files. That terminal state is preserved as `ERC1_DATA_BINDING_INVALID_PRE_PREDICTION`.

ERC-1B changes the **data binding only**. It does not repair, retune, or reinterpret the clean-room compiler based on benchmark outcomes because no ERC-1 benchmark outcome exists.

## Question

Can the independently reimplemented MCO-04 direct transparent compiler reproduce the historical `63/63` scientific root-service localization result when executed against a verified data-bearing RCAEval revision?

## Frozen identities

- Historical MCO-04 RCAEval code commit: `4695aa69f4f1f57b9094ca04ff235908b73a8e24`
- Historical MCO-04 Hugging Face dataset revision from `MCO04_CONFIG.json`: `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e`
- Expected RE3 cases: 90
- Engineering diagnostic: `repetition == 1`, 27 cases
- Scientific reproduction set: `repetition != 1`, 63 cases
- Model calls: 0
- Packet capacity: 16 records

The clean-room compiler implementation must remain byte-identical to the compiler qualified in ERC-1. Any compiler hash change invalidates ERC-1B and requires a new successor rather than a silent refreeze.

## Data-bearing precondition

Before staging, the transport layer must enumerate the exact pinned dataset revision and establish all of the following:

1. exactly 90 paths matching `re3*/metrics.parquet`;
2. exactly 90 paths matching `re3*/inject_time.txt`;
3. one metric file and one injection timestamp for every RE3 case directory;
4. no case outside RE3 enters the downloaded candidate corpus.

The inventory check may observe public repository paths for transport purposes, but it may not produce predictions or scores. Candidate execution receives only the opaque staging output.

If the inventory precondition fails, terminal status is `ERC1B_DATA_BINDING_INVALID_PRE_PREDICTION`. No alternate revision may be substituted inside the same frozen experiment.

## Isolation

Staging converts public source-case directories to deterministic opaque IDs and physically separates:

- `candidate/`: metric telemetry, injection timestamp, representation and SHA-256 provenance;
- `scorer_only/`: source case, system, root-cause service, fault and repetition.

The candidate compiler cannot import or read scorer-only material. Candidate-visible metadata does not include source system, source path, fault, repetition, root-cause service or source case.

The clean-room executable modules may not import or reference `scripts/run_mco04.py` or `tests/test_mco04.py`, and may not consume historical MCO-04 per-case predictions.

## Execution order

1. verify the authorized implementation/data freeze;
2. rerun clean-room regression and firewall tests;
3. enumerate and assert the pinned revision inventory;
4. download only the 90 metric files and 90 injection timestamps;
5. stage opaque candidate/scorer split;
6. compile all 90 predictions once;
7. independently compile the same staged bytes again;
8. require byte-identical live/replay prediction files;
9. only after both seals exist, open scorer-only labels;
10. score the 63 scientific cases and 27 engineering diagnostics;
11. preserve predictions, report, staging manifest and hashes.

## Exact reproduction criterion

ERC-1B reproduces the historical direct-compiler result only if all of the following hold:

- scientific n = 63;
- top-1 = 63/63;
- top-3 = 63/63;
- every system scientific top-1 = 1.0;
- every packet contains at most 16 records;
- provenance checks pass for every packet record;
- live/replay files are byte-identical.

`62/63` is a discrepancy, not a reproduction.

## Outcome precedence

1. `ERC1B_DATA_BINDING_INVALID_PRE_PREDICTION`
2. `ERC1B_OPACITY_OR_PROVENANCE_INVALID`
3. `ERC1B_CLEANROOM_DISCREPANCY`
4. `ERC1B_MCO04_DIRECT_REPRODUCED_PINNED_DATASET`

## Interpretation boundary

A reproduction would establish that the narrow deterministic telemetry-compression/localization mechanism survives an independent implementation and hosted execution against the same pinned RCAEval revision. It would not establish general causal identification, semantic understanding, AGI, a general memory architecture, or cross-domain transfer.

A reproduction advances directly to frozen cross-domain transfer. A discrepancy advances to discrepancy analysis; it does not authorize tuning ERC-1B until it passes.
