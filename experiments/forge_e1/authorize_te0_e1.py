from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.forge.te0_io import file_sha256


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_record(path: Path, expected_status: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != expected_status:
        raise ValueError(f"record status mismatch for {path}: {value.get('status') if isinstance(value, dict) else None}")
    observed = value.get("record_sha256")
    body = {k: v for k, v in value.items() if k != "record_sha256"}
    expected = hashlib.sha256(canonical(body)).hexdigest()
    if observed != expected:
        raise ValueError(f"record digest mismatch: {path}")
    return value


def main() -> None:
    ap = argparse.ArgumentParser(description="Create one-shot TE0-E1 hidden Vault authorization.")
    ap.add_argument("--champion", type=Path, required=True)
    ap.add_argument("--model-identity", type=Path, required=True)
    ap.add_argument("--vault-seed-file", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--vault-count", type=int, default=32)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.vault_count != 32:
        raise ValueError("TE0_E1_VAULT_COUNT_FROZEN_AT_32")

    champion = verify_record(args.champion, "TE0_E1_DEVELOPMENT_CHAMPION_FROZEN")
    identity = verify_record(args.model_identity, "TE0_E1_MODEL_PREFLIGHT_PASS")
    seed_text = args.vault_seed_file.read_text(encoding="utf-8").strip()
    if len(seed_text) < 32:
        raise ValueError("TE0_E1_VAULT_SEED_TOO_SHORT")

    bindings = {
        "champion_file_sha256": file_sha256(args.champion),
        "champion_record_sha256": champion["record_sha256"],
        "model_identity_file_sha256": file_sha256(args.model_identity),
        "model_identity_record_sha256": identity["record_sha256"],
        "vault_seed_file_sha256": file_sha256(args.vault_seed_file),
        "vault_seed_text_sha256": hashlib.sha256(seed_text.encode("utf-8")).hexdigest(),
        "vault_count": args.vault_count,
    }
    record: dict[str, Any] = {
        "schema_version": 1,
        "unit": "TE0-E1",
        "status": "TE0_E1_ONE_RUN_AUTHORIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "executions_authorized": 1,
        "consumed": False,
        "scope": "generate hidden Vault from bound secret seed, collect one raw model output per case, run frozen repair chain, score once",
        "bindings": bindings,
        "thresholds": {
            "vault_exact_rate": 0.95,
            "vault_structural_validity_rate": 0.98,
            "improvement_over_raw": 0.10,
            "margin_over_null": 0.20,
            "preserve_already_valid": 1.0,
        },
        "prohibitions": {
            "second_vault_execution": True,
            "post_vault_tool_search": True,
            "model_substitution": True,
            "prompt_change": True,
            "repair_prompt_access": True,
            "repair_target_access": True,
            "per_case_retry": True,
        },
    }
    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
