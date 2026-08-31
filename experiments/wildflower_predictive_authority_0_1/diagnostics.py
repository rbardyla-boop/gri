"""Engineering-only policy diagnostics and failure-type matrix.

These diagnostics never produce a scientific result.  They use synthetic
machine-native cases and read historical artifacts only to identify missing
observability fields.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Iterable

from . import design
from .authority import AuthorityContext, POLICIES, authority_for, oracle_authority
from .gates import nontriviality


@dataclass(frozen=True)
class DiagnosticCase:
    name: str
    learned_h1_error: float
    null_h1_error: float
    learned_h8_error: float
    null_h8_error: float
    learned_h32_error: float
    null_h32_error: float
    innovation_score: float
    disagreement: float
    current_authority: float
    delayed_authority: float
    expected_behavior: str


def failure_type_cases() -> tuple[DiagnosticCase, ...]:
    """Return the preregistered matrix of predictor/authority edge cases."""

    return (
        DiagnosticCase("learned_better_h1_h8", .60, 1.00, .60, 1.00, .80, 1.00, .50, .10, .80, .80, "use learned authority"),
        DiagnosticCase("learned_better_h1_worse_h8", .60, 1.00, 1.20, 1.00, 1.10, 1.00, .65, .40, .90, .90, "defer at H8"),
        DiagnosticCase("learned_worse_h1_better_h8", 1.20, 1.00, .70, 1.00, .75, 1.00, .40, .20, .70, .70, "do not infer H8 from H1"),
        DiagnosticCase("learned_worse_everywhere", 1.20, 1.00, 1.20, 1.00, 1.20, 1.00, .70, .80, .95, .95, "fail closed"),
        DiagnosticCase("near_tie", 1.01, 1.00, 1.01, 1.00, 1.01, 1.00, .30, .05, .50, .50, "avoid brittle switching"),
        DiagnosticCase("authority_saturation", .90, 1.00, .95, 1.00, .95, 1.00, .80, .10, 1.00, 1.00, "check nontrivial saturation"),
        DiagnosticCase("innovation_spike", .90, 1.00, 1.10, 1.00, 1.05, 1.00, 1.00, .75, .90, .90, "reduce authority"),
        DiagnosticCase("innovation_decline", .80, 1.00, .85, 1.00, .90, 1.00, .20, .10, .40, .40, "recover useful authority"),
        DiagnosticCase("mode_transition", .90, 1.00, 1.10, 1.00, 1.05, 1.00, .70, .55, .90, .90, "condition on current signals"),
        DiagnosticCase("event_rich_interval", .85, 1.00, 1.05, 1.00, 1.00, 1.00, .75, .45, .85, .85, "do not use event truth"),
        DiagnosticCase("recursive_rollout_drift", .80, 1.00, 1.30, 1.00, 1.40, 1.00, .60, .70, .90, .90, "horizon-aware deference"),
        DiagnosticCase("clipping_heavy_rollout", .90, 1.00, 1.15, 1.00, 1.20, 1.00, .70, .65, .90, .90, "reduce authority under clipping"),
        DiagnosticCase("null_learned_crossover", .95, 1.00, .85, 1.00, .90, 1.00, .55, .35, .75, .75, "allow horizon-specific crossover"),
        DiagnosticCase("delayed_recursive_failure", .85, 1.00, 1.05, 1.00, 1.25, 1.00, .55, .60, .85, .85, "avoid delayed drift"),
    )


def _context(case: DiagnosticCase, horizon: int) -> AuthorityContext:
    return AuthorityContext(
        rollout_horizon=horizon,
        horizon_step=0,
        current_authority=case.current_authority,
        delayed_authority=case.delayed_authority,
        innovation_score=case.innovation_score,
        disagreement=case.disagreement,
        instability=case.disagreement,
        residual_history=case.innovation_score,
        saturation_duration=3 if case.current_authority >= .99 else 0,
        state_change=.25,
        recurrence_sensitivity=case.disagreement,
    )


def _mixed(null_error: float, learned_error: float, authority: float) -> float:
    return (1.0 - authority) * null_error + authority * learned_error


def evaluate_failure_matrix(
    cases: Iterable[DiagnosticCase] | None = None,
) -> dict[str, object]:
    """Score static component mixing for diagnostics, not scientific gates."""

    selected = tuple(cases or failure_type_cases())
    rows: list[dict[str, object]] = []
    for case in selected:
        policies: dict[str, object] = {}
        for policy in POLICIES[:-1]:
            policy_row: dict[str, object] = {}
            for horizon, null_error, learned_error in (
                (1, case.null_h1_error, case.learned_h1_error),
                (8, case.null_h8_error, case.learned_h8_error),
                (32, case.null_h32_error, case.learned_h32_error),
            ):
                authority = authority_for(policy, _context(case, horizon))
                policy_row[f"h{horizon}"] = {
                    "authority": authority,
                    "mixed_error": _mixed(null_error, learned_error, authority),
                    "learned_null_ratio": learned_error / null_error,
                }
            policies[policy] = policy_row
        oracle = {
            "h1": oracle_authority(case.null_h1_error, case.learned_h1_error),
            "h8": oracle_authority(case.null_h8_error, case.learned_h8_error),
            "h32": oracle_authority(case.null_h32_error, case.learned_h32_error),
        }
        rows.append(
            {
                "name": case.name,
                "expected_behavior": case.expected_behavior,
                "policies": policies,
                "P6_ORACLE_UPPER_BOUND": oracle,
            }
        )
    return {
        "case_count": len(rows),
        "cases": rows,
        "truth_used_by_mechanism": False,
        "oracle_is_evaluator_only": True,
    }


def degenerate_nontriviality_checks() -> dict[str, object]:
    """Show that authority collapse is rejected before scientific scoring."""

    origin_count = 120
    checks = {
        "NULL_ONLY": [0.0] * origin_count,
        "AUTHORITY_EPSILON_EVERYWHERE": [0.01] * origin_count,
        "EASIEST_MODE_ONLY": [0.5 if index < 40 else 0.0 for index in range(origin_count)],
        "H1_ONLY_H8_ZERO": [0.0] * origin_count,
        "PERMANENTLY_CAPPED_NEAR_ZERO": [0.01] * origin_count,
    }
    result: dict[str, object] = {}
    for name, values in checks.items():
        summary = nontriviality(values)
        result[name] = {
            **summary,
            "collapse_rejected": not bool(summary["passed"]),
        }
    result["EASIEST_MODE_ONLY"]["mode_concentration_warning"] = True
    return result


def audit_historical_artifact(path: Path) -> dict[str, object]:
    """Check whether a frozen artifact contains the new required fields."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("predictive_trace", [])
    if not isinstance(rows, list):
        raise ValueError("historical predictive_trace is not a list")
    first = rows[0] if rows else {}
    return {
        "path": str(path),
        "trace_rows": len(rows),
        "historical_h8_prediction_present": "h8_prediction" in first,
        "learned_only_h8_present": "learned_only_h8_prediction" in first,
        "learned_only_h32_present": "learned_only_h32_prediction" in first,
        "full_h8_counterfactuals_available": "learned_only_h8_prediction" in first,
        "diagnostic_conclusion": (
            "new successor observability is required"
            if "learned_only_h8_prediction" not in first
            else "historical fields are sufficient"
        ),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_engineering_profile() -> dict[str, object]:
    """Run only synthetic engineering diagnostics and frozen-artifact audit."""

    started = time.perf_counter()
    root = Path(__file__).resolve().parents[2]
    historical = (
        root
        / "experiments"
        / "wildflower_dual_authority_0_3"
        / "artifacts"
        / "development_seed340.json"
    )
    matrix = evaluate_failure_matrix()
    return {
        "experiment": "WILDFLOWER Predictive Authority 0.1",
        "status": "ENGINEERING_PROFILE_ONLY",
        "scientific_seed_executed": False,
        "selector_namespace_used": False,
        "historical_artifact_audit": audit_historical_artifact(historical),
        "failure_type_matrix": matrix,
        "degenerate_nontriviality_checks": degenerate_nontriviality_checks(),
        "policies": list(POLICIES),
        "diagnostic_comparators": list(design.DIAGNOSTIC_COMPARATORS),
        "successor_candidates": list(design.SUCCESSOR_CANDIDATES),
        "runtime": {
            "wall_seconds": time.perf_counter() - started,
        },
        "historical_artifact_sha256": _sha256(historical),
    }
