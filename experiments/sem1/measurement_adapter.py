from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

LABELS = (
    "ASSERTED",
    "ENTAILED",
    "PRESUPPOSED",
    "IMPLICATED",
    "CONTRADICTED",
    "UNKNOWN",
)

EVIDENCE_FIELDS = (
    "evidence",
    "evidenceArray",
    "evidenceMultiset",
    "evidence_multiset",
)


class MeasurementUnresolved(ValueError):
    """Candidate output could not be mapped without guessing."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}:{detail}")


@dataclass(frozen=True)
class AdaptationResult:
    status: str
    canonical: dict[str, dict[str, Any]] | None
    code: str | None

    @classmethod
    def resolved(cls, canonical: dict[str, dict[str, Any]]) -> "AdaptationResult":
        return cls("RESOLVED", canonical, None)

    @classmethod
    def unresolved(cls, code: str) -> "AdaptationResult":
        return cls("UNRESOLVED", None, code)


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MeasurementUnresolved("DUPLICATE_JSON_KEY", key)
        out[key] = value
    return out


def strict_json_loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs_object)
    except MeasurementUnresolved:
        raise
    except Exception as exc:
        raise MeasurementUnresolved("JSON_PARSE_ERROR", type(exc).__name__) from exc


def extract_single_balanced_object(text: Any) -> str:
    if not isinstance(text, str):
        raise MeasurementUnresolved("RAW_NOT_TEXT")

    spans: list[tuple[int, int]] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for idx, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = idx
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise MeasurementUnresolved("UNBALANCED_JSON_OBJECT")
            if depth == 0:
                spans.append((start, idx + 1))
                start = None

    if start is not None:
        raise MeasurementUnresolved("INCOMPLETE_JSON_OBJECT")
    if len(spans) != 1:
        raise MeasurementUnresolved("JSON_OBJECT_COUNT", str(len(spans)))
    lo, hi = spans[0]
    return text[lo:hi]


def _normalize_label(raw: Any) -> str:
    if not isinstance(raw, str):
        raise MeasurementUnresolved("LABEL_NOT_TEXT")
    normalized = raw.strip().upper()
    matches = [label for label in LABELS if label == normalized]
    if len(matches) != 1:
        raise MeasurementUnresolved("LABEL_NOT_REGISTERED", raw)
    return matches[0]


def _canonical_evidence_from_value(raw: Any, statement_ids: set[str]) -> tuple[str, ...]:
    if isinstance(raw, list):
        if any(not isinstance(item, str) for item in raw):
            raise MeasurementUnresolved("EVIDENCE_LIST_NONSTRING")
        ids = [item.strip() for item in raw]
    elif isinstance(raw, dict):
        if any(not isinstance(key, str) or not isinstance(value, bool) for key, value in raw.items()):
            raise MeasurementUnresolved("EVIDENCE_MEMBERSHIP_INVALID")
        ids = [key.strip() for key, value in raw.items() if value]
    else:
        raise MeasurementUnresolved("EVIDENCE_REPRESENTATION_INVALID")

    if any(not item for item in ids):
        raise MeasurementUnresolved("EVIDENCE_EMPTY_ID")
    foreign = sorted(set(ids) - statement_ids)
    if foreign:
        raise MeasurementUnresolved("FOREIGN_EVIDENCE_ID", ",".join(foreign))
    return tuple(sorted(set(ids)))


def _extract_evidence(payload: dict[str, Any], statement_ids: set[str]) -> tuple[str, ...]:
    present = [field for field in EVIDENCE_FIELDS if field in payload]
    if not present:
        raise MeasurementUnresolved("EVIDENCE_FIELD_MISSING")

    values = {
        _canonical_evidence_from_value(payload[field], statement_ids)
        for field in present
    }
    if len(values) != 1:
        raise MeasurementUnresolved("CONFLICTING_EVIDENCE_FIELDS")
    return next(iter(values))


def _canonical_prediction_payload(raw: Any, statement_ids: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise MeasurementUnresolved("PREDICTION_NOT_OBJECT")

    # Direct form: {"label": ..., <evidence field>: ...}
    if "label" in raw:
        allowed_keys = {"label", *EVIDENCE_FIELDS}
        extra = sorted(set(raw) - allowed_keys)
        if extra:
            raise MeasurementUnresolved("UNEXPECTED_PREDICTION_KEYS", ",".join(extra))
        label = _normalize_label(raw["label"])
        evidence = _extract_evidence(raw, statement_ids)
        return {"label": label, "evidence": list(evidence)}

    # Nested-label form: {"ASSERTED": {<evidence field>: ...}}
    if len(raw) != 1:
        raise MeasurementUnresolved("PREDICTION_SCHEMA_NOT_RECOVERABLE")
    raw_label, inner = next(iter(raw.items()))
    label = _normalize_label(raw_label)
    if not isinstance(inner, dict):
        raise MeasurementUnresolved("NESTED_LABEL_VALUE_NOT_OBJECT")
    extra = sorted(set(inner) - set(EVIDENCE_FIELDS))
    if extra:
        raise MeasurementUnresolved("UNEXPECTED_NESTED_KEYS", ",".join(extra))
    evidence = _extract_evidence(inner, statement_ids)
    return {"label": label, "evidence": list(evidence)}


def adapt_candidate_output(
    raw_text: Any,
    *,
    proposition_ids: Sequence[str],
    statement_ids: Sequence[str],
) -> AdaptationResult:
    """Map one raw candidate response to a canonical SEM-1 payload.

    The function is deliberately pure and fail-closed. It has no access to a
    prompt, case metadata, gold, files, network, tools, or another model.
    """

    try:
        prop_ids = tuple(str(x) for x in proposition_ids)
        stmt_ids = {str(x) for x in statement_ids}
        if not prop_ids or len(set(prop_ids)) != len(prop_ids):
            raise MeasurementUnresolved("PROPOSITION_ID_CONTRACT_INVALID")
        if len(stmt_ids) != len(tuple(statement_ids)):
            raise MeasurementUnresolved("STATEMENT_ID_CONTRACT_INVALID")

        obj_text = extract_single_balanced_object(raw_text)
        outer = strict_json_loads(obj_text)
        if not isinstance(outer, dict):
            raise MeasurementUnresolved("TOP_LEVEL_NOT_OBJECT")

        if set(outer) == {"predictions"}:
            predictions = outer["predictions"]
        else:
            predictions = outer

        if not isinstance(predictions, dict):
            raise MeasurementUnresolved("PREDICTIONS_NOT_OBJECT")

        expected = set(prop_ids)
        observed = set(predictions)
        missing = sorted(expected - observed)
        foreign = sorted(observed - expected)
        if missing:
            raise MeasurementUnresolved("MISSING_PROPOSITION_ID", ",".join(missing))
        if foreign:
            raise MeasurementUnresolved("FOREIGN_PROPOSITION_ID", ",".join(foreign))

        canonical: dict[str, dict[str, Any]] = {}
        for prop_id in prop_ids:
            canonical[prop_id] = _canonical_prediction_payload(predictions[prop_id], stmt_ids)
        return AdaptationResult.resolved(canonical)

    except MeasurementUnresolved as exc:
        return AdaptationResult.unresolved(exc.code)


def canonical_semantic_equal(left: AdaptationResult, right: AdaptationResult) -> bool:
    """Replay equality requires two resolved, identical canonical payloads."""

    return (
        left.status == "RESOLVED"
        and right.status == "RESOLVED"
        and left.canonical == right.canonical
    )
