from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--candidate-spec", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--selected-adapter", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--min-decisions", type=int, default=10000)
    ap.add_argument("--min-exact-rate", type=float, default=0.999)
    ap.add_argument("--max-structural-failures", type=int, default=0)
    args = ap.parse_args()

    if args.output.exists():
        raise FileExistsError(args.output)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("status") != "MBM_GRINDER_COMPLETE" or report.get("scientific_content") is not False:
        raise ValueError("not a valid non-scientific grinder report")
    ranking = report.get("ranking") or []
    if not ranking:
        raise ValueError("grinder report has no candidates")
    winner = ranking[0]

    gates = {
        "decision_count": winner.get("n", 0) >= args.min_decisions,
        "exact_rate": winner.get("exact_rate", 0.0) >= args.min_exact_rate,
        "structural_failures": winner.get("structural_failures", 10**9) <= args.max_structural_failures,
        "fixture_hash_bound": report.get("fixture_sha256") == file_sha256(args.fixtures),
        "candidate_spec_hash_bound": report.get("candidate_spec_sha256") == file_sha256(args.candidate_spec),
        "adapter_exists": args.selected_adapter.is_file(),
    }
    status = "MBM_ENGINEERING_STACK_FROZEN" if all(gates.values()) else "MBM_ENGINEERING_FREEZE_BLOCKED"

    record = {
        "schema_version": 1,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scientific_evidence": False,
        "winner": winner,
        "gates": gates,
        "bindings": {
            "grinder_report_sha256": file_sha256(args.report),
            "candidate_spec_sha256": file_sha256(args.candidate_spec),
            "fixtures_sha256": file_sha256(args.fixtures),
            "selected_adapter_sha256": file_sha256(args.selected_adapter) if args.selected_adapter.is_file() else None,
        },
        "firewall": {
            "semantic_benchmark_used_for_selection": False,
            "gold_used_for_selection": False,
            "future_science_must_bind_this_record": True,
        },
    }
    record["record_sha256"] = canonical_sha256(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    raise SystemExit(0 if status == "MBM_ENGINEERING_STACK_FROZEN" else 2)


if __name__ == "__main__":
    main()
