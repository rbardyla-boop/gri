# GRI-SIM-0 — Bounded Primitive Laboratory

GRI-SIM-0 is infrastructure for the Small-Info / GRI research branch. It is not a successor mechanism and does not authorize a new scientific claim.

Purpose: make candidate iteration fast while keeping the experiment boundary hard. Candidate code is loaded through a narrow recurrent-cell interface; the simulator owns sequence stepping, training split selection, precision modes, q8 state storage, restart testing, fixed-decoder evaluation, and budget preflight.

Core rule: a run may be convenient, but it is not a scientific verdict unless the experiment manifest, candidate declaration, hashes, accounting audit, replay, and preregistered verdict all pass.

## Commands

```bash
python gri_sim0.py validate-experiment --experiment experiment_manifest.json
python gri_sim0.py validate-candidate --experiment experiment_manifest.json \
  --candidate candidate_manifest.example.json --source candidate_template.py
python gri_sim0.py scaffold --name MY-CANDIDATE --out ./my_candidate
python qualify.py --receipt ../artifacts/results/gri_sim0_qualification_receipt.json
```

The included candidate template intentionally does not implement a research mechanism.

## KC-0 development bank

The separate `kc0/` directory contains a development-only knowledge-cell
fixture bank. It is not part of the frozen GRI-02B reference experiment and
does not extend the candidate protocol or authorize a successor mechanism.

```bash
python kc0/validate_bank.py
```

The validator covers KC-0A through KC-0J packet/query streams and rejects
candidate or scientific authorization fields. Each trial still requires its
own candidate interface, metric thresholds, resource accounting, and
authorization before execution.

`qualify.py` uses a deterministic infrastructure probe and the KC-0
fixture-only adapter. It is a laboratory qualification receipt, not a
candidate run and not a scientific verdict.

## Codex workflow

Give Codex only:

1. `GRI-SIM-0-SPEC.md`
2. `candidate_protocol.py`
3. the experiment manifest
4. a new candidate manifest
5. the explicit authorization for that candidate

Codex should not edit the simulator, frozen experiment manifest, fixture bank, operation rules, or verdict logic during a candidate run.

## Current GRI boundary

The closed GRI-01 → GRI-02C.1 sequence remains unchanged. `GRI-SIM-0` is tooling only. It does not authorize a successor candidate.
