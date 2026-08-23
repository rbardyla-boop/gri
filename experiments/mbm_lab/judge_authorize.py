from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-manifest", type=Path, required=True)
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--recipe-search-report", type=Path, required=True)
    ap.add_argument("--recipe-sha256", required=True)
    ap.add_argument("--min-exact-rate", type=float, default=0.99)
    ap.add_argument("--max-structural-failures", type=int, default=0)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    manifest = json.loads(args.pool_manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "TE0_POOLS_FROZEN":
        raise ValueError("pool manifest not frozen")
    if manifest["pools"]["VAULT"]["sha256"] != fsha(args.vault):
        raise ValueError("VAULT hash mismatch")
    report = json.loads(args.recipe_search_report.read_text(encoding="utf-8"))
    if report.get("status") != "TE0_RECIPE_SEARCH_COMPLETE" or report.get("gold_visible_to_tools") is not False:
        raise ValueError("invalid recipe search report")
    match = [r for r in report.get("ranking", []) if r.get("recipe_sha256") == args.recipe_sha256]
    if len(match) != 1:
        raise ValueError("recipe SHA not uniquely present in report")

    rec = {
        "schema_version": 1,
        "status": "TE0_JUDGE_AUTHORIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "consumed": False,
        "executions_authorized": 1,
        "recipe": match[0]["recipe"],
        "recipe_sha256": args.recipe_sha256,
        "thresholds": {
            "min_exact_rate": args.min_exact_rate,
            "max_structural_failures": args.max_structural_failures,
        },
        "bindings": {
            "pool_manifest_sha256": fsha(args.pool_manifest),
            "vault_sha256": fsha(args.vault),
            "catalog_sha256": fsha(args.catalog),
            "recipe_search_report_sha256": fsha(args.recipe_search_report),
        },
    }
    rec["authorization_record_sha256"] = csha(rec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rec, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
