from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .core import digest


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_SAFE_FACT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CONTROL_TERMS = ("same", "only", "controlled", "matched", "fixed", "shared", "ablation", "baseline")
_ALLOWED_SIGNAL_KINDS = {
    "integrity_failure",
    "transfer_failure",
    "confound",
    "transparent_null",
    "component_unnecessary",
    "strong_baseline_missing",
    "absolute_quality_failure",
    "baseline_dominates",
    "advance",
}


def _clean_cell(value: str) -> str:
    return value.strip().replace("**", "").replace("__", "")


def _cells(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [cell.strip() for cell in raw.split("|")]


def _numeric_values(cell: str) -> list[float]:
    return [float(match.group(0)) for match in _NUMBER_RE.finditer(_clean_cell(cell))]


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _nearest_heading(lines: list[str], before: int) -> str | None:
    for index in range(before - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _context(lines: list[str], start: int, limit: int = 24) -> str:
    begin = max(0, start - limit)
    block = "\n".join(lines[begin:start]).strip()
    return block[-4000:]


def _evidence_requests() -> dict[str, dict[str, str]]:
    return {
        "source_identity": {
            "status": "VERIFIED_FROM_SOURCE",
            "request": "Bind exact source bytes/revision before approval.",
        },
        "candidate_identity": {
            "status": "HUMAN_CONFIRMATION_REQUIRED",
            "request": "Select the candidate row or condition that receives the claimed improvement.",
        },
        "baseline_identity": {
            "status": "HUMAN_CONFIRMATION_REQUIRED",
            "request": "Select the comparator row or condition and confirm it is the relevant baseline.",
        },
        "metric_direction": {
            "status": "HUMAN_CONFIRMATION_REQUIRED",
            "request": "Select metric columns/vector positions and whether higher or lower is better.",
        },
        "baseline_strength": {
            "status": "UNRESOLVED",
            "request": "Establish whether the selected baseline is strong enough for the requested claim.",
        },
        "model_parity": {
            "status": "UNRESOLVED",
            "request": "Establish whether candidate and baseline use matched model/policy capability where required.",
        },
        "budget_parity": {
            "status": "UNRESOLVED",
            "request": "Establish matched action/token/call/compute budgets or explicitly account for the difference.",
        },
        "dataset_split_parity": {
            "status": "UNRESOLVED",
            "request": "Establish that candidate and baseline are evaluated on the same data/split/population.",
        },
        "ablation_isolation": {
            "status": "UNRESOLVED",
            "request": "Establish whether the comparison changes only the mechanism being credited.",
        },
        "source_lineage": {
            "status": "UNRESOLVED",
            "request": "Reconcile any derived, truncated, re-scored, or replayed artifact with its stated source lineage.",
        },
        "uncertainty_replication": {
            "status": "UNRESOLVED",
            "request": "Record uncertainty, repeated runs, or independent replication when the claim requires them.",
        },
    }


def scan_markdown(
    source: str | Path,
    *,
    output: str | Path | None = None,
    source_uri: str | None = None,
    source_revision: str | None = None,
    expected_git_blob_sha1: str | None = None,
) -> dict[str, Any]:
    path = Path(source).resolve()
    payload = path.read_bytes()
    observed_blob = _git_blob_sha1(payload)
    if expected_git_blob_sha1 and observed_blob != expected_git_blob_sha1:
        raise ValueError(
            f"source git blob mismatch: {observed_blob} != {expected_git_blob_sha1}"
        )
    text = payload.decode("utf-8")
    lines = text.splitlines()

    tables: list[dict[str, Any]] = []
    index = 0
    while index + 1 < len(lines):
        line = lines[index]
        if "|" not in line or not _SEPARATOR_RE.match(lines[index + 1]):
            index += 1
            continue
        headers = _cells(line)
        rows: list[dict[str, Any]] = []
        cursor = index + 2
        while cursor < len(lines):
            raw = lines[cursor]
            if "|" not in raw or raw.lstrip().startswith("#") or not raw.strip().startswith("|"):
                break
            cells = _cells(raw)
            if len(cells) != len(headers):
                break
            rows.append(
                {
                    "line": cursor + 1,
                    "cells": cells,
                    "clean_cells": [_clean_cell(cell) for cell in cells],
                    "numeric_cells": {
                        str(column): values
                        for column, cell in enumerate(cells)
                        if (values := _numeric_values(cell))
                    },
                }
            )
            cursor += 1

        if rows:
            context = _context(lines, index)
            normalized_context = " ".join(context.lower().split())
            table = {
                "id": f"table_{len(tables) + 1:03d}",
                "heading": _nearest_heading(lines, index),
                "start_line": index + 1,
                "end_line": cursor,
                "headers": headers,
                "rows": rows,
                "context": context,
                "control_terms": [term for term in _CONTROL_TERMS if term in normalized_context],
            }
            tables.append(table)
        index = max(cursor, index + 2)

    draft: dict[str, Any] = {
        "schema_version": 2,
        "evidence_class": "UNAPPROVED_MARKDOWN_CLAIM_DRAFT",
        "authority_status": "HUMAN_APPROVAL_REQUIRED",
        "source": {
            "path": str(path),
            "uri": source_uri,
            "revision": source_revision,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "git_blob_sha1": observed_blob,
        },
        "table_count": len(tables),
        "tables": tables,
        "evidence_requests": _evidence_requests(),
        "boundary": {
            "candidate_not_inferred": True,
            "baseline_not_inferred": True,
            "metric_direction_not_inferred": True,
            "negative_signal_not_inferred": True,
            "credit_decision_not_run": True,
        },
    }
    draft["draft_sha256"] = digest(draft)
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return draft


def _normalized(value: str) -> str:
    return " ".join(_clean_cell(value).split())


def _select_table(draft: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    table_id = approval.get("table_id")
    heading_contains = approval.get("table_heading_contains")
    headers_include = approval.get("table_headers_include", [])
    if not isinstance(headers_include, list):
        raise ValueError("table_headers_include must be a list")
    candidates = list(draft.get("tables", []))
    if table_id:
        candidates = [table for table in candidates if table.get("id") == table_id]
    if heading_contains:
        needle = str(heading_contains).lower()
        candidates = [
            table for table in candidates if needle in str(table.get("heading") or "").lower()
        ]
    if headers_include:
        wanted = {_normalized(str(header)).lower() for header in headers_include}
        candidates = [
            table
            for table in candidates
            if wanted.issubset({_normalized(str(header)).lower() for header in table.get("headers", [])})
        ]
    if len(candidates) != 1:
        raise ValueError(f"approval must select exactly one table; selected {len(candidates)}")
    return candidates[0]


def _select_row(table: dict[str, Any], column: int, label: str) -> dict[str, Any]:
    wanted = _normalized(label)
    matches = [
        row
        for row in table["rows"]
        if column < len(row["clean_cells"]) and _normalized(row["clean_cells"][column]) == wanted
    ]
    if len(matches) != 1:
        raise ValueError(f"row label {label!r} matched {len(matches)} rows")
    return matches[0]


def _metric_value(row: dict[str, Any], column: int, value_index: int) -> float:
    values = row.get("numeric_cells", {}).get(str(column), [])
    if value_index < 0 or value_index >= len(values):
        raise ValueError(
            f"numeric value index {value_index} unavailable in column {column}; observed {values}"
        )
    return float(values[value_index])


def _repo_root(path: Path) -> Path:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def _toml_literal(value: Any) -> str:
    if value is None:
        raise ValueError("null is not supported in generated autopsy predicates")
    if isinstance(value, (str, bool, int, float)):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError(f"unsupported generated TOML literal: {type(value).__name__}")


def _load_bound_source(draft: dict[str, Any]) -> tuple[bytes, str]:
    path = Path(str(draft["source"]["path"])).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"scanned source no longer exists: {path}")
    payload = path.read_bytes()
    observed_sha256 = hashlib.sha256(payload).hexdigest()
    observed_blob = _git_blob_sha1(payload)
    if observed_sha256 != draft["source"]["sha256"] or observed_blob != draft["source"]["git_blob_sha1"]:
        raise ValueError("scanned source changed after draft creation")
    return payload, payload.decode("utf-8")


def _verify_phrase(full_source: str, phrase: str) -> bool:
    return _normalized(phrase).lower() in _normalized(full_source).lower()


def _approved_facts(approval: dict[str, Any], full_source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_facts = approval.get("approved_facts", [])
    if not isinstance(raw_facts, list):
        raise ValueError("approved_facts must be a list")
    facts: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []
    for fact in raw_facts:
        if not isinstance(fact, dict):
            raise ValueError("approved facts must be objects")
        name = fact.get("name")
        phrase = fact.get("source_phrase")
        if not isinstance(name, str) or not _SAFE_FACT_RE.fullmatch(name):
            raise ValueError("approved fact name must be a safe identifier")
        if name in facts:
            raise ValueError(f"duplicate approved fact: {name}")
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError(f"approved fact {name} requires source_phrase")
        value = fact.get("value")
        _toml_literal(value)
        found = _verify_phrase(full_source, phrase)
        checks.append({"name": name, "value": value, "source_phrase": phrase, "found": found})
        if not found:
            raise ValueError(f"approved fact source phrase missing: {name}")
        facts[name] = {
            "value": value,
            "source_phrase": phrase,
            "source_phrase_verified": True,
        }
    return facts, checks


def _approval_signals(approval: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
    raw_signals = approval.get("signals", [])
    if not isinstance(raw_signals, list):
        raise ValueError("signals must be a list")
    signals: list[dict[str, Any]] = []
    for signal in raw_signals:
        if not isinstance(signal, dict):
            raise ValueError("approval signals must be objects")
        kind = signal.get("kind")
        mode = signal.get("mode", "all")
        predicates = signal.get("predicates")
        if kind not in _ALLOWED_SIGNAL_KINDS:
            raise ValueError(f"unsupported approval signal kind: {kind}")
        if mode not in {"all", "any"}:
            raise ValueError("approval signal mode must be all or any")
        if not isinstance(predicates, list) or not predicates:
            raise ValueError("approval signal requires predicates")
        rows: list[dict[str, Any]] = []
        for predicate in predicates:
            if not isinstance(predicate, dict):
                raise ValueError("approval signal predicates must be objects")
            fact_name = predicate.get("fact")
            if not isinstance(fact_name, str) or fact_name not in facts:
                raise ValueError(f"approval signal references unknown fact: {fact_name}")
            expected = predicate.get("equals", facts[fact_name]["value"])
            _toml_literal(expected)
            rows.append({"fact": fact_name, "equals": expected})
        signals.append(
            {
                "id": str(signal.get("id", kind)),
                "kind": kind,
                "mode": mode,
                "note": signal.get("note"),
                "predicates": rows,
            }
        )
    return signals


def materialize_approved_markdown_claim(
    draft_path: str | Path,
    approval_path: str | Path,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    draft_path = Path(draft_path).resolve()
    approval_path = Path(approval_path).resolve()
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    approval = json.loads(approval_path.read_text(encoding="utf-8"))

    if approval.get("approved") is not True:
        raise ValueError("approval must contain approved=true")
    if draft.get("authority_status") != "HUMAN_APPROVAL_REQUIRED":
        raise ValueError("input is not an unapproved Markdown claim draft")
    expected_blob = approval.get("source_git_blob_sha1")
    if not isinstance(expected_blob, str) or expected_blob != draft["source"]["git_blob_sha1"]:
        raise ValueError("approval source_git_blob_sha1 does not bind the scanned source")
    expected_revision = approval.get("source_revision")
    if expected_revision is not None and expected_revision != draft["source"].get("revision"):
        raise ValueError("approval source_revision does not match the draft")

    _, full_source = _load_bound_source(draft)
    table = _select_table(draft, approval)
    row_label_column = int(approval.get("row_label_column", 0))
    candidate_label = approval.get("candidate_label")
    baseline_label = approval.get("baseline_label")
    if not isinstance(candidate_label, str) or not isinstance(baseline_label, str):
        raise ValueError("approval requires candidate_label and baseline_label")
    candidate_row = _select_row(table, row_label_column, candidate_label)
    baseline_row = _select_row(table, row_label_column, baseline_label)

    phrases = approval.get("required_source_phrases", [])
    if not isinstance(phrases, list):
        raise ValueError("required_source_phrases must be a list")
    phrase_checks: list[dict[str, Any]] = []
    for phrase in phrases:
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError("source phrases must be non-empty strings")
        found = _verify_phrase(full_source, phrase)
        phrase_checks.append({"phrase": phrase, "found": found})
    if not all(item["found"] for item in phrase_checks):
        missing = [item["phrase"] for item in phrase_checks if not item["found"]]
        raise ValueError(f"approved source phrase missing: {missing}")

    metrics = approval.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("approval requires one or more metrics")
    metric_rows: dict[str, Any] = {}
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("metric approvals must be objects")
        name = metric.get("name")
        direction = metric.get("direction", "greater")
        if not isinstance(name, str) or not _SAFE_FACT_RE.fullmatch(name):
            raise ValueError("metric name must be a safe identifier")
        if direction not in {"greater", "less"}:
            raise ValueError("each metric requires direction greater|less")
        column = int(metric["column"])
        value_index = int(metric.get("value_index", 0))
        candidate_value = _metric_value(candidate_row, column, value_index)
        baseline_value = _metric_value(baseline_row, column, value_index)
        signed_delta = candidate_value - baseline_value
        improvement = signed_delta if direction == "greater" else -signed_delta
        metric_rows[name] = {
            "column": column,
            "value_index": value_index,
            "direction": direction,
            "candidate": candidate_value,
            "baseline": baseline_value,
            "signed_delta": signed_delta,
            "improvement": improvement,
            "minimum_improvement": float(metric.get("minimum_improvement", 0.0)),
        }

    facts, fact_checks = _approved_facts(approval, full_source)
    approved_signals = _approval_signals(approval, facts)

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "evidence.json"
    spec_path = output_dir / "autopsy.toml"
    receipt_path = output_dir / "approval_receipt.json"

    evidence: dict[str, Any] = {
        "schema_version": 2,
        "evidence_class": "HUMAN_APPROVED_MARKDOWN_EXTRACTION",
        "source": draft["source"],
        "draft_sha256": draft["draft_sha256"],
        "selected_table": {
            "id": table["id"],
            "heading": table.get("heading"),
            "start_line": table["start_line"],
            "end_line": table["end_line"],
            "headers": table.get("headers"),
        },
        "comparison": {
            "candidate_label": candidate_label,
            "baseline_label": baseline_label,
            "metrics": metric_rows,
        },
        "controls": {
            "source_phrases_verified": all(item["found"] for item in phrase_checks),
            "phrases": phrase_checks,
        },
        "facts": facts,
        "fact_checks": fact_checks,
        "evidence_requests": draft.get("evidence_requests", {}),
        "approval": {
            "approved": True,
            "reviewer_statement": approval.get("reviewer_statement"),
            "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
        },
        "boundary": {
            "human_selected_comparison": True,
            "human_selected_negative_signals": bool(approved_signals),
            "automatic_credit_authority": False,
            "prospective_evidence": False,
        },
    }
    evidence["evidence_sha256"] = digest(evidence)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    root = _repo_root(output_dir)
    try:
        evidence_ref = str(evidence_path.relative_to(root))
    except ValueError:
        evidence_ref = str(evidence_path)

    credit_target = str(approval.get("credit_target", "human-approved Markdown comparison"))
    claim_if_advance = str(
        approval.get("claim_if_advance", "the human-approved comparison retains provisional conditional credit")
    )
    claim_if_not_advance = str(
        approval.get("claim_if_not_advance", "the human-approved comparison does not establish mechanism credit")
    )

    lines = [
        "[autopsy]",
        f"id = {_toml_literal(str(approval.get('autopsy_id', 'generated-markdown-autopsy')))}",
        f"credit_target = {_toml_literal(credit_target)}",
        f"claim_if_advance = {_toml_literal(claim_if_advance)}",
        f"claim_if_not_advance = {_toml_literal(claim_if_not_advance)}",
        "",
        "[sources]",
        f"evidence = {_toml_literal(evidence_ref)}",
        "",
    ]

    if approval.get("include_advance_signal", True):
        lines.extend(
            [
                "[[signals]]",
                'id = "human-approved-controlled-comparison"',
                'kind = "advance"',
                'mode = "all"',
                'note = "Generated from a content-bound Markdown draft after explicit human approval."',
                "predicates = [",
                '  { source = "evidence", path = "controls.source_phrases_verified", op = "eq", value = true },',
            ]
        )
        for name, row in metric_rows.items():
            lines.append(
                "  { source = \"evidence\", path = "
                + _toml_literal(f"comparison.metrics.{name}.improvement")
                + ", op = \"gte\", value = "
                + _toml_literal(float(row["minimum_improvement"]))
                + " },"
            )
        lines.extend(["]", ""])

    for signal in approved_signals:
        lines.extend(
            [
                "[[signals]]",
                f"id = {_toml_literal(signal['id'])}",
                f"kind = {_toml_literal(signal['kind'])}",
                f"mode = {_toml_literal(signal['mode'])}",
            ]
        )
        if signal.get("note") is not None:
            lines.append(f"note = {_toml_literal(str(signal['note']))}")
        lines.append("predicates = [")
        for predicate in signal["predicates"]:
            lines.append(
                "  { source = \"evidence\", path = "
                + _toml_literal(f"facts.{predicate['fact']}.value")
                + ", op = \"eq\", value = "
                + _toml_literal(predicate["equals"])
                + " },"
            )
        lines.extend(["]", ""])

    spec_path.write_text("\n".join(lines), encoding="utf-8")

    receipt = {
        "schema_version": 2,
        "draft_path": str(draft_path),
        "approval_path": str(approval_path),
        "evidence_path": str(evidence_path),
        "autopsy_spec_path": str(spec_path),
        "draft_sha256": draft["draft_sha256"],
        "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
        "evidence_sha256": evidence["evidence_sha256"],
        "approved_fact_count": len(facts),
        "approved_signal_count": len(approved_signals),
        "authority_status": "READY_FOR_UNCHANGED_AUTOPSY_ENGINE",
    }
    receipt["receipt_sha256"] = digest(receipt)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt
