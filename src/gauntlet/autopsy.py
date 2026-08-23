from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import digest, load_spec, lookup, read_json


# Fixed claim-credit precedence. These are generic evidence classes, not
# experiment-specific verdict labels.
OUTCOME_PRECEDENCE = (
    "INTEGRITY_INVALID",
    "TRANSFER_FAILURE",
    "CONFOUND_EXPLAINS_ADVANTAGE",
    "TRANSPARENT_NULL_DOMINATES",
    "COMPONENT_UNNECESSARY",
    "STRONG_BASELINE_MISSING",
    "ABSOLUTE_QUALITY_FAILURE",
    "BASELINE_DOMINATES",
    "ADVANCE",
)

SIGNAL_TO_OUTCOME = {
    "integrity_failure": "INTEGRITY_INVALID",
    "transfer_failure": "TRANSFER_FAILURE",
    "confound": "CONFOUND_EXPLAINS_ADVANTAGE",
    "transparent_null": "TRANSPARENT_NULL_DOMINATES",
    "component_unnecessary": "COMPONENT_UNNECESSARY",
    "strong_baseline_missing": "STRONG_BASELINE_MISSING",
    "absolute_quality_failure": "ABSOLUTE_QUALITY_FAILURE",
    "baseline_dominates": "BASELINE_DOMINATES",
    "advance": "ADVANCE",
}

CREDIT_DISPOSITION = {
    "INTEGRITY_INVALID": "UNASSESSED",
    "TRANSFER_FAILURE": "WITHHELD",
    "CONFOUND_EXPLAINS_ADVANTAGE": "REMOVED",
    "TRANSPARENT_NULL_DOMINATES": "REMOVED",
    "COMPONENT_UNNECESSARY": "REMOVED",
    "STRONG_BASELINE_MISSING": "WITHHELD",
    "ABSOLUTE_QUALITY_FAILURE": "WITHHELD",
    "BASELINE_DOMINATES": "REMOVED",
    "ADVANCE": "PROVISIONAL",
    "UNRESOLVED": "WITHHELD",
}

_ALLOWED_KINDS = set(SIGNAL_TO_OUTCOME)
_ALLOWED_OPS = {
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "truthy",
    "falsey",
    "approx_eq",
    "path_gt",
    "path_gte",
    "path_lt",
    "path_lte",
    "path_approx_eq",
}


def _resolve_spec_path(spec_path: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    # Autopsy specs are repository artifacts. Resolve sources relative to the
    # repository root if one exists, otherwise relative to the spec directory.
    current = spec_path.parent.resolve()
    root = current
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            root = candidate
            break
    return (root / path).resolve()


def _number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{label} must resolve to a number")
    return float(value)


def _load_sources(spec_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    raw_sources = spec.get("sources")
    if not isinstance(raw_sources, dict) or not raw_sources:
        raise ValueError("autopsy spec requires [sources]")
    loaded: dict[str, Any] = {}
    for name, raw in raw_sources.items():
        if not isinstance(name, str) or not isinstance(raw, str):
            raise ValueError("autopsy sources must map names to JSON paths")
        path = _resolve_spec_path(spec_path, raw)
        if not path.is_file():
            raise FileNotFoundError(path)
        loaded[name] = read_json(path)
    return loaded


def _value(sources: dict[str, Any], source: str, path: str) -> Any:
    if source not in sources:
        raise KeyError(f"unknown source: {source}")
    return lookup(sources[source], path)


def _eval_predicate(predicate: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    source = predicate.get("source")
    path = predicate.get("path")
    op = predicate.get("op", "eq")
    if not isinstance(source, str) or not isinstance(path, str):
        raise ValueError("predicate requires source and path")
    if op not in _ALLOWED_OPS:
        raise ValueError(f"unsupported autopsy predicate op: {op}")

    observed = _value(sources, source, path)
    expected: Any = predicate.get("value")
    other_observed: Any = None
    tolerance = float(predicate.get("tolerance", 0.0))

    if op == "eq":
        passed = observed == expected
    elif op == "ne":
        passed = observed != expected
    elif op == "truthy":
        passed = bool(observed)
    elif op == "falsey":
        passed = not bool(observed)
    elif op in {"gt", "gte", "lt", "lte", "approx_eq"}:
        left = _number(observed, f"{source}.{path}")
        right = _number(expected, "predicate value")
        if op == "gt":
            passed = left > right
        elif op == "gte":
            passed = left >= right
        elif op == "lt":
            passed = left < right

        elif op == "lte":
            passed = left <= right
        else:
            passed = abs(left - right) <= tolerance
    else:
        other_source = predicate.get("other_source")
        other_path = predicate.get("other_path")
        if not isinstance(other_source, str) or not isinstance(other_path, str):
            raise ValueError(f"{op} requires other_source and other_path")
        other_observed = _value(sources, other_source, other_path)
        left = _number(observed, f"{source}.{path}")
        right = _number(other_observed, f"{other_source}.{other_path}")
        if op == "path_gt":
            passed = left > right
        elif op == "path_gte":
            passed = left >= right
        elif op == "path_lt":
            passed = left < right
        elif op == "path_lte":
            passed = left <= right
        else:
            passed = abs(left - right) <= tolerance

    row: dict[str, Any] = {
        "source": source,
        "path": path,
        "op": op,
        "observed": observed,
        "pass": passed,
    }
    if op not in {"truthy", "falsey"}:
        if op.startswith("path_"):
            row["other_source"] = predicate.get("other_source")
            row["other_path"] = predicate.get("other_path")
            row["other_observed"] = other_observed
        else:
            row["expected"] = expected
    if "approx_eq" in op:
        row["tolerance"] = tolerance
    return row


def _validate_signal(signal: dict[str, Any]) -> None:
    kind = signal.get("kind")
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"unsupported autopsy signal kind: {kind}")
    predicates = signal.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise ValueError(f"signal {kind} requires predicates")
    if signal.get("mode", "all") not in {"all", "any"}:
        raise ValueError("signal mode must be all or any")


def autopsy_claim(spec_path: str | Path) -> dict[str, Any]:
    spec_path = Path(spec_path).resolve()
    spec = load_spec(spec_path)
    meta = spec.get("autopsy")
    if not isinstance(meta, dict):
        raise ValueError("autopsy spec requires [autopsy]")
    claim_id = meta.get("id")
    credit_target = meta.get("credit_target")
    if not isinstance(claim_id, str) or not isinstance(credit_target, str):
        raise ValueError("[autopsy] requires id and credit_target")

    sources = _load_sources(spec_path, spec)
    raw_signals = spec.get("signals", [])
    if not isinstance(raw_signals, list) or not raw_signals:
        raise ValueError("autopsy spec requires [[signals]]")

    evaluated: list[dict[str, Any]] = []
    triggered_outcomes: list[str] = []
    for signal in raw_signals:
        if not isinstance(signal, dict):
            raise ValueError("signals must be tables")
        _validate_signal(signal)
        rows = [_eval_predicate(predicate, sources) for predicate in signal["predicates"]]
        mode = signal.get("mode", "all")
        triggered = all(row["pass"] for row in rows) if mode == "all" else any(row["pass"] for row in rows)
        outcome = SIGNAL_TO_OUTCOME[str(signal["kind"])]
        evaluated.append(
            {
                "id": signal.get("id", signal["kind"]),
                "kind": signal["kind"],
                "mode": mode,
                "triggered": triggered,
                "outcome_if_triggered": outcome,
                "predicates": rows,
                "note": signal.get("note"),
            }
        )
        if triggered:
            triggered_outcomes.append(outcome)

    outcome = "UNRESOLVED"
    for candidate in OUTCOME_PRECEDENCE:
        if candidate in triggered_outcomes:
            outcome = candidate
            break

    # A claimed advance is never allowed to override a higher-precedence
    # negative/invalidating signal.
    strongest_claim = meta.get("claim_if_advance") if outcome == "ADVANCE" else meta.get("claim_if_not_advance")
    if not isinstance(strongest_claim, str):
        strongest_claim = (
            "claim receives provisional mechanism credit"
            if outcome == "ADVANCE"
            else "requested mechanism-level claim is not established"
        )

    result: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": "RETROSPECTIVE_MECHANISM_AUTOPSY",
        "autopsy_id": claim_id,
        "credit_target": credit_target,
        "outcome": outcome,
        "credit_disposition": CREDIT_DISPOSITION.get(outcome, "WITHHELD"),
        "strongest_claim": strongest_claim,
        "triggered_outcomes": triggered_outcomes,
        "signals": evaluated,
        "boundary": {
            "prospective_credit": False,
            "reason": "retrospective mechanism autopsy can validate generic diagnosis logic but cannot create new preregistered scientific evidence",
        },
    }
    result["autopsy_sha256"] = digest(result)
    return result
