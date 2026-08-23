# GRI-SIM-0 Integration

`GRI-SIM-0 — Bounded Primitive Laboratory` is now installed under `sim/` as
permanent GRI infrastructure.

## Provenance

```text
source bundle: GRI-SIM-0.zip
bundle SHA-256: 8ffd166a7f9a9f0f5a894230c1c38a14d74c0364331ba1314f2c2d81a3dc0493
```

The eight copied bundle files match the source archive byte-for-byte. The
installed simulator and protocol are tooling only; they do not authorize a
successor mechanism or alter the frozen GRI-01 → GRI-02C.1 result.

## Installed boundary

```text
sim/gri_sim0.py
sim/candidate_protocol.py
sim/candidate_template.py
sim/experiment_manifest.json
sim/candidate_manifest.example.json
sim/GRI-SIM-0-SPEC.md
sim/CODEX_HANDOFF.md
sim/README.md
sim/runtime.py
sim/qualify.py
sim/kc0/trial_bank.json
sim/kc0/validate_bank.py
sim/kc0/dev_smoke.py
sim/kc0/kc1a/cell.py
sim/kc0/kc1a/manifest.json
sim/kc0/kc1a/lifecycle.py
sim/kc0/kc1b/config.json
sim/kc0/kc1b/characterize.py
sim/kc0/kc1c/config.json
sim/kc0/kc1c/characterize.py
sim/kc0/kc1d/config.json
sim/kc0/kc1d/characterize.py
sim/kc2a/__init__.py
sim/kc2a/config.json
sim/kc2a/transfer.py
sim/kc2a/characterize.py
sim/kc2b/__init__.py
sim/kc2b/config.json
sim/kc2b/export.py
sim/kc2b/characterize.py
sim/kc2c/__init__.py
sim/kc2c/config.json
sim/kc2c/protocol.py
sim/kc2c/characterize.py
sim/kc2d/__init__.py
sim/kc2d/config.json
sim/kc2d/spawn.py
sim/kc2d/characterize.py
sim/kc3a/__init__.py
sim/kc3a/config.json
sim/kc3a/manager.py
sim/kc3a/characterize.py
sim/kc3b/__init__.py
sim/kc3b/config.json
sim/kc3b/share.py
sim/kc3b/characterize.py
sim/kc3c/__init__.py
sim/kc3c/config.json
sim/kc3c/activate.py
sim/kc3c/characterize.py
```

The reference manifest points to the existing frozen GRI-02B contract,
configuration, fixture bank, operation rules, and harness by their recorded
hashes. Candidate code cannot self-certify a formal budget advantage: an
independent accounting audit is required, and an internal semantic selector
is candidate cost.

## Qualification

The reusable shell is qualified by:

```bash
python3 sim/qualify.py \
  --receipt artifacts/results/gri_sim0_qualification_receipt.json
```

The qualification checks canonical budget-key handling, malformed-manifest
failure, token/state-only recurrence, fixed-decoder fitting, every-boundary
serialization/restart, deterministic replay, unauthorized-candidate
rejection, and the KC-0 fixture adapter. It uses an infrastructure probe cell;
it is not a candidate run and emits `scientific_verdict: FORBIDDEN`.

The current qualification receipt has file SHA-256:

```text
109f87baf18f385f4ff3c8956eb4d6eb576539eb2cae60f87519233976bc628d
```

## Validation

The infrastructure tests verify that:

- the reference experiment manifest passes preflight;
- the unauthorized template fails closed for missing authorization, hashes,
  resource declarations, and accounting audit;
- scaffolding creates an explicitly non-authorizing candidate directory.

Development smoke remains distinct from a frozen scientific run. The current
canonical scientific boundary remains:

```text
GRI-02C:   ALGORITHMIC FINDING SUPPORTED
GRI-02C.1: FORMAL GRI02_NO_ADVANTAGE
MINIMALITY: NOT ESTABLISHED
SUCCESSOR:  NOT AUTHORIZED
```

The current project-level state reconciliation is maintained in
`docs/PROJECT-STATE-RECONCILIATION.md`. It records the terminal
`GRI_05_SO4_NO_ADVANTAGE` result and `RRI_01_RELATION_ERASURE` diagnosis. The
remaining open question is the parent minimality problem; the reconciliation
authorizes no execution.

KC-2A-D is installed as a development-only two-cell transfer
characterization. It uses two unchanged KC-1A instances and a stateless
transfer adapter; it does not add replication or population logic and does
not change the scientific ledger.

KC-2B-D is installed as a development-only oracle-free state-export
characterization. It adds no candidate mechanism and keeps KC-1A unchanged;
the export adapter derives payloads from source state plus physical slot only,
with zero declared coordinator state.

KC-2C-D is installed as a development-only cooperative overflow
characterization. It composes two unchanged KC-1A cells with the frozen
KC-2B exporter, uses no persistent coordinator state, and does not add
replication or population logic.

KC-2D-D is installed as a development-only bounded child-creation
characterization. It creates one fresh KC-1A child per explicit call from
parent state through the frozen KC-2B exporter; automatic spawning,
population registries, and population logic remain absent.

KC-3A-D is installed as a development-only bounded population lifecycle
characterization. It adds only lifecycle metadata for explicit in-memory
cells, with hard population/generation caps; knowledge remains in cell state
and no automatic population dynamics are present.

KC-3B-D is installed as a development-only scheduled knowledge-spread
characterization over the frozen KC-3A lifecycle. It adds no cells or
registry fields; explicit source/target/slot contacts only move transient
payloads through existing cell states.

KC-3C-D is installed as a development-only local contact-selection
characterization. Explicit activation derives occupied slots and live
parent/child neighbors locally, then delegates delivery to KC-3B; it adds no
policy state, automatic activation, or registry fields.

KC-3D-D is installed as a development-only bounded population-tick
characterization. One explicit tick snapshots the canonical live-cell
schedule, prevalidates all scheduled states, and invokes KC-3C exactly once per
start-of-tick live cell. It adds no persistent scheduler state, background
execution, cell creation, cell death, or registry mutation; the hard bounds are
eight activations and 112 slot-contact attempts per tick.

KC-3E-D is installed as a development-only finite-horizon population-dynamics
characterization over frozen KC-3D. The harness executes exactly four explicit
ticks, records t0..t4 population snapshots, and restarts from each boundary. It
adds no reusable automatic runner, background execution, population mutation,
or scientific threshold; total work is bounded at 32 activations and 448
slot-contact attempts.

KC-3F-D is installed as a development-only scheduler-counterfactual
characterization beside frozen KC-3D. It compares four preregistered
deterministic activation orders using unchanged KC-3C contact behavior; the
canonical order must reproduce KC-3D. It adds no adaptive or random scheduler,
persistent order state, population mutation, background execution, fitness,
selection, or scientific verdict.

KC-4A-D is installed as a development-only equal-budget distributed-memory
utility benchmark. It compares eight existing KC-1A cells against a simple
centralized 64-slot baseline using frozen KC-3D dynamics and six exact failure,
pressure, distribution, and conflict cases. It records recovery, loss,
communication, operations, restart, and replay without an advantage threshold,
learning, or scientific verdict.

KC-4B-D is installed as a development-only capacity/redundancy frontier
characterization. It freezes one, two, four, and eight copies per identity in
the same 64 physical positions, compares unchanged KC-3D dynamics with an
equally redundant static 64-address baseline, and tests all eight single-cell
loss cases before and after the four-tick horizon. It records identity
retention, copy counts, utilization, contacts, operations, restart, and replay
without changing routing or adding a scientific threshold/verdict.

`docs/KC-BRANCH-1-CLOSURE.md` archives the complete KC-1A → KC-4B development
branch. The branch is closed after the equal-budget utility failure; no KC-4C
or successor mechanics are authorized. Any future reopening requires a new,
bounded collision-routing hypothesis that directly targets diversity collapse.
