from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from experiments.forge.te0_io import file_sha256

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "te0_e0"


def run(module: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", module, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline public TE0-E0 sandbox qualification. Not scientific evidence.")
    ap.add_argument("--scratch", type=Path, default=Path("/scratch/te0-e0"))
    args = ap.parse_args()
    root = args.scratch.resolve()
    root.mkdir(parents=True, exist_ok=True)

    paths = {
        "champion": root / "champion.json",
        "authorization": root / "authorization.json",
        "consumed": root / "vault-consumed.json",
        "receipt": root / "judge-receipt.json",
        "skill": root / "qualification-skill.json",
        "ledger": root / "ledger.jsonl",
        "summary": root / "TE0_E0_QUALIFICATION.json",
    }
    existing = [str(p) for p in paths.values() if p.exists()]
    if existing:
        raise SystemExit(f"TE0_E0_SCRATCH_NOT_FRESH: {existing}")

    run(
        "experiments.forge.te0_dev",
        "--build", str(FIX / "build.jsonl"),
        "--dev", str(FIX / "dev.jsonl"),
        "--signals", str(FIX / "signals.json"),
        "--input-kind", "text",
        "--output-kind", "label",
        "--max-depth", "4",
        "--max-cost", "4",
        "--output", str(paths["champion"]),
        "--ledger", str(paths["ledger"]),
    )
    champion = json.loads(paths["champion"].read_text(encoding="utf-8"))
    if champion["champion"]["dev_score"] != 1.0:
        raise SystemExit("TE0_E0_DEV_NOT_PERFECT")
    tools = set(champion["champion"]["tools"])
    if "ts_build_lookup_canonical" not in tools or "ts_lower" not in tools or not tools.intersection({"ts_strip", "ts_normalize_space"}):
        raise SystemExit(f"TE0_E0_EXPECTED_MULTI_TOOL_REPAIR_NOT_FOUND:{sorted(tools)}")

    run(
        "experiments.forge.te0_authorize",
        "--champion", str(paths["champion"]),
        "--vault", str(FIX / "public_test_vault.jsonl"),
        "--threshold", "1.0",
        "--min-margin-over-null", "0.5",
        "--output", str(paths["authorization"]),
    )

    judged = run(
        "experiments.forge.te0_judge",
        "--champion", str(paths["champion"]),
        "--vault", str(FIX / "public_test_vault.jsonl"),
        "--authorization", str(paths["authorization"]),
        "--consume-marker", str(paths["consumed"]),
        "--receipt", str(paths["receipt"]),
        "--skill-output", str(paths["skill"]),
        "--ledger", str(paths["ledger"]),
    )
    outcome = json.loads(judged.stdout)
    if outcome.get("verdict") != "PASS" or outcome.get("score") != 1.0 or outcome.get("skill_promoted") is not True:
        raise SystemExit(f"TE0_E0_JUDGE_FAILED:{outcome}")

    second = run(
        "experiments.forge.te0_judge",
        "--champion", str(paths["champion"]),
        "--vault", str(FIX / "public_test_vault.jsonl"),
        "--authorization", str(paths["authorization"]),
        "--consume-marker", str(paths["consumed"]),
        "--receipt", str(root / "second-receipt.json"),
        check=False,
    )
    if second.returncode == 0 or "TE0_VAULT_ALREADY_CONSUMED" not in second.stdout:
        raise SystemExit("TE0_E0_SECOND_VAULT_RUN_NOT_BLOCKED")

    summary = {
        "schema_version": 1,
        "unit": "TE0-E0",
        "status": "TE0_E0_PIPELINE_QUALIFIED",
        "scientific": False,
        "qualification_only": True,
        "network_required": False,
        "candidate_model_calls": 0,
        "vault_fixture_public": True,
        "development_vault_access": False,
        "judge_verdict": outcome["verdict"],
        "judge_score": outcome["score"],
        "second_vault_attempt_blocked": True,
        "champion_chain_id": champion["champion"]["chain_id"],
        "champion_tools": champion["champion"]["tools"],
        "artifacts": {
            key: {"path": str(path), "sha256": file_sha256(path)}
            for key, path in paths.items()
            if key != "summary" and path.exists()
        },
    }
    paths["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
