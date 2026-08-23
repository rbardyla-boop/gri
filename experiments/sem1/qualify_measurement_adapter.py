from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from experiments.sem1.measurement_adapter import LABELS, adapt_candidate_output


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_for(label: str, suffix: int) -> dict[str, dict[str, Any]]:
    a = f"S{suffix:03d}A"
    b = f"S{suffix:03d}B"
    return {
        "P1": {"label": label, "evidence": [a, b]},
        "P2": {"label": "UNKNOWN", "evidence": []},
    }


def ids_for(suffix: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return ("P1", "P2"), (f"S{suffix:03d}A", f"S{suffix:03d}B", f"S{suffix:03d}C")


def direct_payload(expected: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {k: dict(v) for k, v in expected.items()}


def positive_forms(expected: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    p1 = expected["P1"]
    p2 = expected["P2"]
    label = p1["label"]
    ev = p1["evidence"]
    direct = direct_payload(expected)

    return [
        ("canonical_direct", json.dumps(direct)),
        ("predictions_wrapper", json.dumps({"predictions": direct})),
        ("prose_wrapper", f"Result follows. {json.dumps(direct)} End."),
        ("label_case_space", json.dumps({
            "P1": {"label": f" {label.lower()} ", "evidence": ev},
            "P2": {"label": " unknown ", "evidence": []},
        })),
        ("duplicate_evidence", json.dumps({
            "P1": {"label": label, "evidence": [ev[1], ev[0], ev[0]]},
            "P2": p2,
        })),
        ("evidence_array", json.dumps({
            "P1": {"label": label, "evidenceArray": list(reversed(ev))},
            "P2": {"label": "UNKNOWN", "evidenceArray": []},
        })),
        ("evidence_multiset_camel", json.dumps({
            "P1": {"label": label, "evidenceMultiset": [ev[0], ev[1], ev[0]]},
            "P2": {"label": "UNKNOWN", "evidenceMultiset": []},
        })),
        ("evidence_multiset_snake", json.dumps({
            "P1": {"label": label, "evidence_multiset": [ev[1], ev[0], ev[1]]},
            "P2": {"label": "UNKNOWN", "evidence_multiset": []},
        })),
        ("boolean_membership", json.dumps({
            "P1": {"label": label, "evidence": {ev[0]: True, ev[1]: True}},
            "P2": {"label": "UNKNOWN", "evidence": {ev[0]: False, ev[1]: False}},
        })),
        ("nested_label", json.dumps({
            "P1": {label: {"evidence": list(ev)}},
            "P2": {"UNKNOWN": {"evidence": []}},
        })),
        ("nested_label_multiset", json.dumps({
            "P1": {label.lower(): {"evidence_multiset": [ev[1], ev[0], ev[0]]}},
            "P2": {" unknown ": {"evidenceMultiset": []}},
        })),
        ("consistent_redundant_fields", json.dumps({
            "P1": {"label": label, "evidence": list(ev), "evidenceArray": list(reversed(ev)), "evidenceMultiset": [ev[0], ev[1], ev[0]]},
            "P2": {"label": "UNKNOWN", "evidence": [], "evidence_multiset": []},
        })),
    ]


def duplicate_key_text(label: str, ev: list[str]) -> str:
    return (
        '{"P1":{"label":"' + label + '","label":"UNKNOWN","evidence":' + json.dumps(ev) + '},'
        '"P2":{"label":"UNKNOWN","evidence":[]}}'
    )


def negative_forms(expected: dict[str, dict[str, Any]], suffix: int) -> list[tuple[str, str]]:
    p1 = expected["P1"]
    p2 = expected["P2"]
    label = p1["label"]
    ev = p1["evidence"]
    foreign_stmt = f"S{suffix:03d}FOREIGN"

    return [
        ("two_json_objects", json.dumps(expected) + " " + json.dumps(expected)),
        ("conflicting_evidence_fields", json.dumps({
            "P1": {"label": label, "evidenceMultiset": [], "evidenceArray": list(ev)},
            "P2": p2,
        })),
        ("foreign_evidence", json.dumps({
            "P1": {"label": label, "evidence": [ev[0], foreign_stmt]},
            "P2": p2,
        })),
        ("foreign_proposition", json.dumps({**expected, "P3": {"label": "UNKNOWN", "evidence": []}})),
        ("missing_proposition", json.dumps({"P1": p1})),
        ("bad_label", json.dumps({
            "P1": {"label": "MAYBE", "evidence": ev},
            "P2": p2,
        })),
        ("missing_evidence", json.dumps({
            "P1": {"label": label},
            "P2": p2,
        })),
        ("duplicate_json_key", duplicate_key_text(label, ev)),
        ("extra_prediction_key", json.dumps({
            "P1": {"label": label, "evidence": ev, "confidence": 1.0},
            "P2": p2,
        })),
        ("unexpected_nested_key", json.dumps({
            "P1": {label: {"evidence": ev, "note": "x"}},
            "P2": {"UNKNOWN": {"evidence": []}},
        })),
        ("nonstring_evidence", json.dumps({
            "P1": {"label": label, "evidence": [ev[0], 7]},
            "P2": p2,
        })),
        ("no_json_object", "I decline to return JSON."),
    ]


def run_qualification() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    positive_total = positive_pass = 0
    negative_total = negative_pass = 0

    for idx, label in enumerate(LABELS, start=1):
        expected = expected_for(label, idx)
        proposition_ids, statement_ids = ids_for(idx)

        for name, raw in positive_forms(expected):
            positive_total += 1
            result = adapt_candidate_output(raw, proposition_ids=proposition_ids, statement_ids=statement_ids)
            ok = result.status == "RESOLVED" and result.canonical == expected
            positive_pass += int(ok)
            rows.append({
                "kind": "POSITIVE",
                "name": name,
                "label": label,
                "raw_sha256": sha256_bytes(raw.encode("utf-8")),
                "status": result.status,
                "code": result.code,
                "ok": ok,
            })

        for name, raw in negative_forms(expected, idx):
            negative_total += 1
            result = adapt_candidate_output(raw, proposition_ids=proposition_ids, statement_ids=statement_ids)
            ok = result.status == "UNRESOLVED"
            negative_pass += int(ok)
            rows.append({
                "kind": "NEGATIVE",
                "name": name,
                "label": label,
                "raw_sha256": sha256_bytes(raw.encode("utf-8")),
                "status": result.status,
                "code": result.code,
                "ok": ok,
            })

    replay_rows = []
    for row in rows:
        replay_rows.append({k: row[k] for k in sorted(row)})
    deterministic_digest = sha256_bytes(canonical_bytes(replay_rows))

    positive_rate = positive_pass / positive_total
    negative_rate = negative_pass / negative_total
    status = (
        "SEM1_MEASUREMENT_QUALIFICATION_PASS"
        if positive_rate == 1.0 and negative_rate == 1.0
        else "SEM1_MEASUREMENT_QUALIFICATION_FAIL"
    )

    report = {
        "schema_version": 1,
        "unit": "SEM-1-MEASUREMENT",
        "status": status,
        "scientific_semantic_content": False,
        "scientific_model_calls": 0,
        "positive": {"n": positive_total, "pass": positive_pass, "rate": positive_rate},
        "negative": {"n": negative_total, "pass": negative_pass, "rate": negative_rate},
        "deterministic_fixture_result_sha256": deterministic_digest,
        "rows": rows,
    }
    report["record_sha256"] = sha256_bytes(canonical_bytes(report))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Qualify the pure SEM-1 measurement adapter on non-semantic fixtures.")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    report = run_qualification()
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "SEM1_MEASUREMENT_QUALIFICATION_PASS" else 2)


if __name__ == "__main__":
    main()
