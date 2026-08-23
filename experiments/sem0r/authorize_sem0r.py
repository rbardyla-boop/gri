from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def verify_identity(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get("status") != "SEM0R_MODEL_PREFLIGHT_PASS":
        raise ValueError("model identity is not a passing SEM-0R preflight record")
    if value.get("scientific_run_authorized") is not False:
        raise ValueError("preflight identity must not itself authorize science")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(value.get("artifact_sha256", ""))):
        raise ValueError("model artifact SHA-256 is missing or malformed")
    observed = value.get("identity_record_sha256")
    body = {k: v for k, v in value.items() if k not in {"identity_record_sha256", "status", "scientific_run_authorized", "next_gate"}}
    if observed != digest(body):
        raise ValueError("model identity digest mismatch")
    return value


def verify_manifest(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get("status") != "SEM0R_INSTRUMENT_FROZEN":
        raise ValueError("instrument manifest is not frozen")
    observed = value.get("manifest_sha256")
    body = {k: v for k, v in value.items() if k != "manifest_sha256"}
    if observed != digest(body):
        raise ValueError("instrument manifest digest mismatch")
    return value


def create_authorization(
    *,
    manifest_path: Path,
    identity_path: Path,
    cases_path: Path,
    replay_cases_path: Path,
    ablation_cases_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite authorization: {output_path}")
    manifest = verify_manifest(manifest_path)
    identity = verify_identity(identity_path)

    dataset_bindings = manifest.get("generated_artifacts", {})
    observed = {
        "cases_sha256": file_sha256(cases_path),
        "replay_cases_sha256": file_sha256(replay_cases_path),
        "ablation_cases_sha256": file_sha256(ablation_cases_path),
    }
    required = {
        "cases_sha256": dataset_bindings.get("cases", {}).get("sha256"),
        "replay_cases_sha256": dataset_bindings.get("replay_cases", {}).get("sha256"),
        "ablation_cases_sha256": dataset_bindings.get("ablation_cases", {}).get("sha256"),
    }
    mismatches = {k: {"manifest": required[k], "observed": observed[k]} for k in observed if required[k] != observed[k]}
    if mismatches:
        raise ValueError(f"generated-artifact binding mismatch: {mismatches}")

    record: dict[str, Any] = {
        "schema_version": 1,
        "unit": "SEM-0R",
        "status": "SEM0R_ONE_RUN_AUTHORIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "executions_authorized": 1,
        "consumed": False,
        "scientific_scope": "one complete SEM-0R live+replay+context-ablation execution under the frozen instrument",
        "bindings": {
            "instrument_manifest_sha256": file_sha256(manifest_path),
            "instrument_manifest_record_sha256": manifest["manifest_sha256"],
            "model_identity_sha256": file_sha256(identity_path),
            "model_identity_record_sha256": identity["identity_record_sha256"],
            **observed,
        },
        "prohibitions": {
            "development_model_runs": 0,
            "post_result_tuning": True,
            "scientific_retries_after_consumption": True,
            "model_substitution": True,
            "threshold_or_scorer_change": True,
        },
    }
    record["authorization_record_sha256"] = digest(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model-identity", type=Path, required=True)
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--replay-cases", type=Path, required=True)
    ap.add_argument("--ablation-cases", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    value = create_authorization(
        manifest_path=args.manifest.resolve(),
        identity_path=args.model_identity.resolve(),
        cases_path=args.cases.resolve(),
        replay_cases_path=args.replay_cases.resolve(),
        ablation_cases_path=args.ablation_cases.resolve(),
        output_path=args.output.resolve(),
    )
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
