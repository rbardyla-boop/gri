from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

LABELS = ("ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN")

THRESHOLDS = {
    "accuracy": {"op": ">=", "value": 0.78},
    "macro_f1": {"op": ">=", "value": 0.72},
    "revision_pair_accuracy": {"op": ">=", "value": 0.78},
    "invariance_pair_accuracy": {"op": ">=", "value": 0.78},
    "unknown_overclaim_rate": {"op": "<=", "value": 0.18},
    "evidence_dependency_f1": {"op": ">=", "value": 0.65},
    "nonce_world_accuracy": {"op": ">=", "value": 0.75},
    "worst_family_accuracy": {"op": ">=", "value": 0.65},
    "scalar_pragmatics_accuracy": {"op": ">=", "value": 0.75},
    "presupposition_accuracy": {"op": ">=", "value": 0.75},
    "abductive_restraint_accuracy": {"op": ">=", "value": 0.75},
    "shortcut_margin": {"op": ">=", "value": 0.15},
    "context_dependency_gap": {"op": ">=", "value": 0.20},
    "exact_replay_rate": {"op": "=", "value": 1.00},
    "integrity_errors": {"op": "=", "value": 0},
}

MODEL_VISIBLE_CASE_KEYS = ("context", "propositions")
MODEL_VISIBLE_STATEMENT_KEYS = ("id", "text")
MODEL_VISIBLE_PROPOSITION_KEYS = ("id", "text")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def model_view(case: dict[str, Any]) -> dict[str, Any]:
    """Return the strict model-visible projection. No experiment metadata crosses this boundary."""
    return {
        "context": [{k: row[k] for k in MODEL_VISIBLE_STATEMENT_KEYS} for row in case["context"]],
        "propositions": [{k: row[k] for k in MODEL_VISIBLE_PROPOSITION_KEYS} for row in case["propositions"]],
    }


def prediction_template(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "predictions": [
            {"proposition_id": row["id"], "label": "UNKNOWN", "evidence": []}
            for row in case["propositions"]
        ]
    }


def validate_prediction_payload(case: dict[str, Any], payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload_not_object"]
    if set(payload) != {"predictions"}:
        errors.append("unexpected_top_level_keys")
    rows = payload.get("predictions")
    if not isinstance(rows, list):
        return errors + ["predictions_not_list"]
    expected_pids = {p["id"] for p in case["propositions"]}
    valid_evidence = {s["id"] for s in case["context"]}
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"prediction_{i}_not_object")
            continue
        if set(row) != {"proposition_id", "label", "evidence"}:
            errors.append(f"prediction_{i}_unexpected_keys")
        pid = row.get("proposition_id")
        if pid not in expected_pids:
            errors.append(f"prediction_{i}_unknown_proposition")
        elif pid in seen:
            errors.append(f"prediction_{i}_duplicate_proposition")
        else:
            seen.add(pid)
        if row.get("label") not in LABELS:
            errors.append(f"prediction_{i}_invalid_label")
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"prediction_{i}_evidence_not_list")
        else:
            if len(evidence) != len(set(evidence)):
                errors.append(f"prediction_{i}_duplicate_evidence")
            if any(eid not in valid_evidence for eid in evidence):
                errors.append(f"prediction_{i}_foreign_evidence")
    if seen != expected_pids:
        errors.append("missing_predictions")
    return errors


def payload_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["proposition_id"]: row for row in payload["predictions"]}
