#!/usr/bin/env python3
"""Qualify GRI-SIM-0 infrastructure without running a research candidate."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import torch
from torch import nn

try:  # Support both ``python -m sim.qualify`` and ``python sim/qualify.py``.
    from .gri_sim0 import read_budgets, validate_candidate, validate_experiment
    from .kc0.dev_smoke import run as run_kc0_smoke
    from .runtime import fit_fixed_decoder, replay_recurrent_trace, run_recurrent_trace
except ImportError:  # pragma: no cover - exercised by the direct CLI path.
    from gri_sim0 import read_budgets, validate_candidate, validate_experiment
    from kc0.dev_smoke import run as run_kc0_smoke
    from runtime import fit_fixed_decoder, replay_recurrent_trace, run_recurrent_trace


ROOT = Path(__file__).resolve().parent
EXPERIMENT = ROOT / "experiment_manifest.json"
KC0_BANK = ROOT / "kc0" / "trial_bank.json"


class QualificationCell(nn.Module):
    """Infrastructure probe, not a research candidate."""

    state_width = 2

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        value = token_ids.to(dtype=state.dtype).unsqueeze(1)
        return state + torch.cat([value, value * 2], dim=1)

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        return state

    def serialize_state(self, state: torch.Tensor) -> bytes:
        buffer = io.BytesIO()
        torch.save(state.detach().cpu(), buffer)
        return buffer.getvalue()

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        value = torch.load(io.BytesIO(payload), map_location=device, weights_only=True)
        return value.to(dtype=dtype, device=device)


def qualify() -> dict:
    reference = validate_experiment(EXPERIMENT)
    unauthorized_candidate = validate_candidate(
        EXPERIMENT,
        ROOT / "candidate_manifest.example.json",
        ROOT / "candidate_template.py",
    )
    malformed = json.loads(EXPERIMENT.read_text(encoding="utf-8"))
    del malformed["budgets"]["recurrent_plus_query_operations_max"]
    _, budget_errors = read_budgets(malformed)
    trace = run_recurrent_trace(QualificationCell, [1, 2, 3], query_positions=[1])
    replay = replay_recurrent_trace(QualificationCell, [1, 2, 3], query_positions=[1])
    decoder = fit_fixed_decoder([[0.0, 0.0], [2.0, 2.0]], ["a", "b"])
    decoder_pass = decoder.predict([[0.1, 0.0], [1.9, 2.0]]) == ["a", "b"]
    kc0 = run_kc0_smoke(KC0_BANK)
    checks = {
        "reference_manifest": reference["status"] == "PASS",
        "missing_budget_fails_closed": bool(budget_errors),
        "unauthorized_candidate_fails_closed": unauthorized_candidate["status"] == "FAIL",
        "restart_trace": trace["status"] == "PASS",
        "deterministic_replay": replay["status"] == "PASS" and replay["matched"],
        "fit_only_decoder": decoder_pass,
        "kc0_fixture_smoke": kc0["status"] == "PASS" and kc0["scientific_verdict"] == "FORBIDDEN",
    }
    return {
        "unit": "GRI-SIM-0-QUALIFICATION",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "candidate_present": False,
        "scientific_execution": "FORBIDDEN",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "reference_preflight": reference,
        "candidate_preflight": {
            "status": unauthorized_candidate["status"],
            "error_count": len(unauthorized_candidate["errors"]),
            "errors": unauthorized_candidate["errors"],
        },
        "budget_regression": {"status": "PASS" if budget_errors else "FAIL", "errors": budget_errors},
        "runtime_trace": {"status": trace["status"], "restart_cases": trace["restart_cases"], "trace_sha256": trace["trace_sha256"]},
        "runtime_replay": {"status": replay["status"], "matched": replay["matched"], "trace_sha256": replay["first_trace_sha256"]},
        "kc0_fixture_smoke": {"status": kc0["status"], "trial_count": kc0["trial_count"], "bank_sha256": kc0["bank_sha256"]},
        "note": "Infrastructure qualification only; the probe cell is not a research candidate.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = qualify()
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"unit": receipt["unit"], "status": receipt["status"], "scientific_verdict": receipt["scientific_verdict"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
