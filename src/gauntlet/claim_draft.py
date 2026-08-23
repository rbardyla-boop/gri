from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .core import canonical, digest


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_CONTROL_TERMS = ("same", "only", "controlled", "matched", "fixed", "shared", "ablation", "baseline")


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
        "schema_version": 1,
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
        "boundary": {
            "candidate_not_inferred": True,
            "baseline_not_inferred": True,
            "metric_direction_not_inferred": True,
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
    candidates = list(draft.get("tables", []))
    if table_id:
        candidates = [table for table in candidates if table.get("id") == table_id]
    if heading_contains:
        needle = str(heading_contains).lower()
        candidates = [
            table for table in candidates if needle in str(table.get("heading") or "").lower()
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


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


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
    normalized_context = _normalized(str(table.get("context", ""))).lower()
    phrase_checks: list[dict[str, Any]] = []
    for phrase in phrases:
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError("source phrases must be non-empty strings")
        found = _normalized(phrase).lower() in normalized_context
        phrase_checks.append({"phrase": phrase, "found": found})
    if not all(item["found"] for item in phrase_checks):
        missing = [item["phrase"] for item in phrase_checks if not item["found"]]
        raise ValueError(f"approved control phrase missing from selected table context: {missing}")

    metrics = approval.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("approval requires one or more metrics")
    metric_rows: dict[str, Any] = {}
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("metric approvals must be objects")
        name = metric.get("name")
        direction = metric.get("direction", "greater")
        if not isinstance(name, str) or direction not in {"greater", "less"}:
            raise ValueError("each metric requires name and direction greater|less")
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

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "evidence.json"
    spec_path = output_dir / "autopsy.toml"
    receipt_path = output_dir / "approval_receipt.json"

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": "HUMAN_APPROVED_MARKDOWN_EXTRACTION",
        "source": draft["source"],
        "draft_sha256": draft["draft_sha256"],
        "selected_table": {
            "id": table["id"],
            "heading": table.get("heading"),
            "start_line": table["start_line"],
            "end_line": table["end_line"],
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
        "approval": {
            "approved": True,
            "reviewer_statement": approval.get("reviewer_statement"),
            "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
        },
        "boundary": {
            "human_selected_comparison": True,
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
        f"id = {_toml_string(str(approval.get('autopsy_id', 'generated-markdown-autopsy')))}",
        f"credit_target = {_toml_string(credit_target)}",
        f"claim_if_advance = {_toml_string(claim_if_advance)}",
        f"claim_if_not_advance = {_toml_string(claim_if_not_advance)}",
        "",
        "[sources]",
        f"evidence = {_toml_string(evidence_ref)}",
        "",
        "[[signals]]",
        'id = "human-approved-controlled-comparison"',
        'kind = "advance"',
        'mode = "all"',
        'note = "Generated from a content-bound Markdown draft after explicit human approval."',
        "predicates = [",
        '  { source = "evidence", path = "controls.source_phrases_verified", op = "eq", value = true },',
    ]
    for name, row in metric_rows.items():
        lines.append(
            "  { source = \"evidence\", path = "
            + _toml_string(f"comparison.metrics.{name}.improvement")
            + ", op = \"gt\", value = "
            + repr(float(row["minimum_improvement"]))
            + " },"
        )
    lines.extend(["]", ""])
    spec_path.write_text("\n".join(lines), encoding="utf-8")

    receipt = {
        "schema_version": 1,
        "draft_path": str(draft_path),
        "approval_path": str(approval_path),
        "evidence_path": str(evidence_path),
        "autopsy_spec_path": str(spec_path),
        "draft_sha256": draft["draft_sha256"],
        "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
        "evidence_sha256": evidence["evidence_sha256"],
        "authority_status": "READY_FOR_UNCHANGED_AUTOPSY_ENGINE",
    }
    receipt["receipt_sha256"] = digest(receipt)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt
