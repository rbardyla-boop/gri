# WILDFLOWER-0 authority replication 230 preregistration

Status: **frozen before fresh replication execution**.

This is a replication of the Nursery-1 innovation-triggered authority result. It does not authorize an architecture freeze, an AGI claim, or opening `PRIMITIVE-0` by itself.

## Frozen candidate

The candidate implementation is byte-locked to:

- `probe_innovation_model.py` SHA-256 `97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1`
- `qualify_authority190.py` SHA-256 `13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e`
- original seed-190 qualification artifact SHA-256 `eec6229a4dae2f94917a8c942b64876e718386456c183332baa6a6b737fb66e0`
- original seed-190 semantic receipt `44fd012e748897b20e5eb94998f33d7ba49fdc1af8439e0bd52a30520f001215`

No candidate model, training rule, authority formula, threshold, width, or decay may change for replication 230.

## Fresh set

- model seed: `230`
- balanced hidden-mode training episodes: `2` per mode
- balanced hidden-mode test episodes: `2` per mode
- training selector root: `MODEL_SEED + 9000`, start offset `400000`
- test selector root: `MODEL_SEED + 19000`, start offset `450000`
- episode length: `420` training / `520` evaluation
- training steps per episode: `80`
- authority burn history: `12`

The exact episode IDs are generated only when the authorized runner executes. Hidden mode may be used only by the generator-side stratifier and evaluator; it is forbidden learner input.

## Frozen authority configuration

- innovation threshold: `0.30` cells
- transition width: `0.30` cells
- open-loop authority decay: `0.998` per predicted step

Authority is computed only from learner-visible numeric prediction innovation. It may blend the learned proposal with the transparent velocity null; it may not read hidden mode or evaluator-only event flags.

## Core replication gates

All six are conjunctive:

1. worst h1 ratio versus velocity null `<= 1.10`
2. worst h8 ratio `<= 1.00`
3. mean h8 ratio `<= 0.90`
4. worst h32 ratio `<= 1.00`
5. mean h32 ratio `<= 0.85`
6. event-window mean h8 ratio `<= 0.90`

A miss is a replication failure. No same-set parameter repair is allowed.

## Preregistered controls

The fresh set also evaluates, from the start:

- velocity-only null;
- the same learned model with no external authority boundary;
- innovation-carry transparent control;
- acceleration-carry transparent control;
- 50/50 innovation-plus-acceleration transparent control.

The three transparent controls use the same frozen numeric innovation threshold, width, and decay as the candidate, but no learned correction.

For mechanism credit, in addition to all six core gates:

- candidate mean h8 ratio must beat the strongest transparent control by at least `0.05`;
- candidate mean h32 ratio must beat the strongest transparent control by at least `0.05`;
- ungated learned model must violate the h1 safety boundary (`> 1.10` worst) while the authority candidate stays `<= 1.10` worst.

If the replication passes but these mechanism gates do not, record `REPLICATION_PASS_MECHANISM_UNRESOLVED`; do not promote the authority mechanism.

## Surprise trajectories

The same held-out episode seeds are also replayed with deterministic surprise injections enabled. Surprise results are descriptive only and cannot rescue or invalidate the registered deterministic qualification.

## Replay and result handling

The authorized hosted execution runs the exact runner twice. Byte-identical output is required for deterministic replay. A scientific/engineering FAIL is a valid completed execution and must not be tuned away. The result is preserved as an artifact before any successor is designed.

`PRIMITIVE-0` remains unopened until a promotion-gate PASS is observed and separately reviewed.
