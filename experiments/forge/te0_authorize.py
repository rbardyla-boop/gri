from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.forge.forge import sha256_json
from experiments.forge.te0_io import file_sha256


def main() -> None:
    ap = argparse.ArgumentParser(description="Bind one TE0 Vault evaluation to one frozen champion and Vault file.")
    ap.add_argument("--champion", type=Path, required=True)
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--threshold", type=float, required=True)
    ap.add_argument("--min-margin-over-null", type=float, default=0.0)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite authorization: {args.output}")
    manifest = json.loads(args.champion.read_text(encoding="utf-8"))
    if manifest.get("unit") != "TE0" or manifest.get("phase") != "DEVELOPMENT" or manifest.get("authority") is not False:
        raise ValueError("champion manifest is not a TE0 development artifact")
    if manifest.get("vault_seen") is not False:
        raise ValueError("development manifest claims Vault exposure")

    body = {
        "schema_version": 1,
        "unit": "TE0",
        "status": "TE0_VAULT_ONE_RUN_AUTHORIZED",
        "executions_authorized": 1,
        "consumed": False,
        "bindings": {
            "champion_manifest_sha256": file_sha256(args.champion),
            "champion_chain_id": manifest["champion"]["chain_id"],
            "vault_sha256": file_sha256(args.vault),
        },
        "threshold": args.threshold,
        "min_margin_over_null": args.min_margin_over_null,
        "prohibitions": {
            "composer_vault_access": True,
            "toolsmith_vault_access": True,
            "post_vault_retuning_under_same_experiment": True,
            "second_vault_execution": True,
        },
    }
    auth = {**body, "authorization_record_sha256": sha256_json(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(auth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(auth, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
