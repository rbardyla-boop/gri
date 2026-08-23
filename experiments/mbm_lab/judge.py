from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from recipe_search import load_catalog, load_jsonl, run_recipe


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_obj(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def consume(auth_path: Path, auth: dict, receipt_path: Path) -> dict:
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    body = {k: v for k, v in auth.items() if k != "authorization_record_sha256"}
    if auth.get("authorization_record_sha256") != csha(body):
        raise ValueError("authorization digest mismatch")
    if auth.get("status") != "TE0_JUDGE_AUTHORIZED" or auth.get("consumed") is not False or auth.get("executions_authorized") != 1:
        raise ValueError("judge authorization invalid or consumed")
    new = dict(auth)
    new["consumed"] = True
    new["consumed_at"] = datetime.now(timezone.utc).isoformat()
    new["status"] = "TE0_JUDGE_CONSUMED"
    new.pop("authorization_record_sha256", None)
    new["authorization_record_sha256"] = csha(new)
    tmp = auth_path.with_suffix(auth_path.suffix + ".tmp")
    tmp.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, auth_path)
    receipt = {
        "status": "TE0_JUDGE_STARTED",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "authorization_sha256_after_consumption": fsha(auth_path),
        "vault_items_attempted": 0,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorization", type=Path, required=True)
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--pool-manifest", type=Path, required=True)
    ap.add_argument("--recipe-search-report", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    auth = load_obj(args.authorization)
    bindings = auth.get("bindings", {})
    observed = {
        "pool_manifest_sha256": fsha(args.pool_manifest),
        "vault_sha256": fsha(args.vault),
        "catalog_sha256": fsha(args.catalog),
        "recipe_search_report_sha256": fsha(args.recipe_search_report),
    }
    mismatch = {k: {"bound": bindings.get(k), "observed": v} for k, v in observed.items() if bindings.get(k) != v}
    if mismatch:
        raise ValueError(f"judge binding mismatch: {mismatch}")

    pool_manifest = load_obj(args.pool_manifest)
    if pool_manifest.get("pools", {}).get("VAULT", {}).get("sha256") != observed["vault_sha256"]:
        raise ValueError("VAULT does not match frozen pool manifest")
    search_report = load_obj(args.recipe_search_report)
    if search_report.get("gold_visible_to_tools") is not False:
        raise ValueError("recipe search allowed gold exposure")
    matches = [r for r in search_report.get("ranking", []) if r.get("recipe_sha256") == auth.get("recipe_sha256")]
    if len(matches) != 1 or matches[0].get("recipe") != auth.get("recipe"):
        raise ValueError("authorized recipe not bound to search report")

    catalog = load_catalog(args.catalog)
    recipe = auth["recipe"]
    if any(name not in catalog or not catalog[name]["promotable"] for name in recipe):
        raise ValueError("recipe contains missing or non-promotable tool")

    receipt = consume(args.authorization, auth, args.receipt)
    fixtures = load_jsonl(args.vault)
    exact = 0
    structural = 0
    rows = []
    try:
        for ordinal, fixture in enumerate(fixtures):
            receipt["vault_items_attempted"] = ordinal + 1
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            prediction, trace, latency, ok = run_recipe(recipe, catalog, fixture, args.timeout)
            is_exact = ok and prediction == fixture["target"]
            exact += int(is_exact)
            structural += int(not ok)
            rows.append({
                "ordinal": ordinal,
                "fixture_id": fixture["id"],
                "exact": is_exact,
                "structural_failure": not ok,
                "prediction_sha256": csha(prediction) if ok else None,
                "target_sha256": csha(fixture["target"]),
                "latency_seconds": latency,
                "trace": trace,
            })
    except Exception as exc:
        receipt.update({
            "status": "TE0_JUDGE_TERMINATED",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise

    n = len(fixtures)
    exact_rate = exact / n if n else 0.0
    thresholds = auth["thresholds"]
    gates = {
        "exact_rate": exact_rate >= thresholds["min_exact_rate"],
        "structural_failures": structural <= thresholds["max_structural_failures"],
    }
    verdict = "PASS" if all(gates.values()) else "FAIL"
    result = {
        "schema_version": 1,
        "status": "TE0_JUDGE_COMPLETE",
        "verdict": verdict,
        "recipe": recipe,
        "recipe_sha256": auth["recipe_sha256"],
        "vault_n": n,
        "exact": exact,
        "exact_rate": exact_rate,
        "structural_failures": structural,
        "thresholds": thresholds,
        "gates": gates,
        "bindings": observed,
        "rows": rows,
        "nonclaims": [
            "TE0 is engineering validation, not evidence of semantic understanding or consciousness.",
            "PASS means the frozen recipe generalized to the hidden synthetic VAULT under the registered gates.",
        ],
    }
    result["judge_record_sha256"] = csha(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt.update({"status": "TE0_JUDGE_COMPLETE", "ended_at": datetime.now(timezone.utc).isoformat(), "verdict": verdict})
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "verdict", "vault_n", "exact_rate", "structural_failures", "judge_record_sha256")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
