from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/dmc04ra"
HISTORICAL_COMMIT = "b057f10"
AMENDMENT_BASE_COMMIT = "c98e0a0"
DMC04P_COMMIT = "61c9ab9"
DMC04PA_TERMINAL = "DMC_04PA_FIXED_DECODER_PREREGISTERED"
HISTORICAL_TERMINAL = "DMC_04R_REPAIR_REQUIRED"
EVIDENCE_SEEDS = [1337, 1338, 1339, 1340, 1341]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_diff_clean(commit: str, path: str) -> bool:
    result = subprocess.run(["git", "diff", "--exit-code", commit, "--", path], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return result.returncode == 0


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing manifest"]}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {str(path.relative_to(root)): sha256(path) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    errors = [f"missing-or-hash:{name}" for name, value in expected.items() if actual.get(name) != value]
    errors.extend(f"unexpected:{name}" for name in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "entries": len(expected), "errors": errors}


def terminal_in(path: Path, expected: str) -> bool:
    for candidate in sorted(path.glob("*RECEIPT.json")) + sorted(path.glob("*VERDICT.json")):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("terminal_state") == expected:
            return True
    return False


def main() -> int:
    historical_path = ROOT / "artifacts/dmc04r"
    amendment_path = ROOT / "artifacts/dmc04pa"
    historical = {
        "commit": HISTORICAL_COMMIT,
        "artifact_path": "artifacts/dmc04r",
        "unchanged_since_historical_commit": git_diff_clean(HISTORICAL_COMMIT, "artifacts/dmc04r"),
        "manifest": verify_manifest(historical_path),
        "terminal": HISTORICAL_TERMINAL,
        "terminal_present": terminal_in(historical_path, HISTORICAL_TERMINAL),
    }
    amendment = {
        "commit": AMENDMENT_BASE_COMMIT,
        "artifact_path": "artifacts/dmc04pa",
        "unchanged_since_amendment_commit": git_diff_clean(AMENDMENT_BASE_COMMIT, "artifacts/dmc04pa"),
        "manifest": verify_manifest(amendment_path),
        "terminal": DMC04PA_TERMINAL,
        "terminal_present": terminal_in(amendment_path, DMC04PA_TERMINAL),
    }
    source = (ROOT / "scripts/run_dmc04r.py").read_text(encoding="utf-8")
    evaluator = {
        "pass": all(token in source for token in ("DMC04R_CORRECTED_EVALUATOR", "selected descriptor group has no temporally eligible record", "missing_as_miss", "return None", "missing_retrieval")),
        "old": "selected descriptor group -> no temporally eligible record -> raise ValueError -> abort experiment",
        "new": "selected descriptor group -> no temporally eligible record -> retrieval_hit=0 -> predicted_answer=null -> continue evaluation",
        "caught_exception": "ValueError with exact message only",
        "other_exceptions_propagate": True,
        "corrected_execution_namespace": "DMC04R_CORRECTED_EVALUATOR=1",
        "corrected_artifact_namespace": "artifacts/dmc04r2",
    }
    pconfig = json.loads((ROOT / "artifacts/dmc04p/DMC04P_CONFIG.json").read_text(encoding="utf-8"))
    paconfig = json.loads((ROOT / "artifacts/dmc04pa/DMC04PA_CONFIG.json").read_text(encoding="utf-8"))
    protocol = {
        "pass": pconfig["evidence_seeds"] == EVIDENCE_SEEDS and pconfig["training"] == {"batch_size": 64, "device": "cpu", "epochs": 80, "gradient_clip": 1.0, "group_level_cross_entropy": True, "learning_rate": 0.01, "optimizer": "AdamW", "torch_threads": 1, "train_split_only": True, "weight_decay": 0.0} and pconfig["model_parameters"] == 128 and paconfig["fixed_decoder"]["seed"] == 1337,
        "evidence_seeds": EVIDENCE_SEEDS,
        "training": pconfig["training"],
        "retriever_parameters": pconfig["model_parameters"],
        "fixed_decoder_seed": paconfig["fixed_decoder"]["seed"],
        "no_data_change": True,
        "no_threshold_change": True,
        "no_architecture_change": True,
        "no_hyperparameter_change": True,
    }
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    full_tests = {"command": "python3 -m pytest -q", "pass": tests.returncode == 0, "returncode": tests.returncode, "last_output": tests.stdout[-2500:]}
    checks = {"historical_identity": historical["unchanged_since_historical_commit"] and historical["manifest"]["pass"] and historical["terminal_present"], "amendment_identity": amendment["unchanged_since_amendment_commit"] and amendment["manifest"]["pass"] and amendment["terminal_present"], "evaluator_semantics": evaluator["pass"], "protocol_identity": protocol["pass"], "full_tests": full_tests["pass"]}
    terminal = "DMC_04RA_FIXED_MISSING_RETRIEVAL_PREREGISTERED" if all(checks.values()) else "DMC_04RA_REPAIR_REQUIRED"
    contract = """# DMC-04R-A — Fixed Missing-Retrieval Evaluation Semantics\n\nStatus: **AMENDMENT PREREGISTERED; FRESH DMC-04R2 EXECUTION AUTHORIZED**\n\nThis additive amendment preserves historical `DMC_04R_REPAIR_REQUIRED` and\nchanges only the evaluator treatment of one frozen resolver condition.\n\nOld behavior:\n\n```text\nselected descriptor group\n→ no temporally eligible record\n→ raise ValueError\n→ abort experiment\n```\n\nNew behavior:\n\n```text\nselected descriptor group\n→ no temporally eligible record\n→ retrieval_hit = 0\n→ predicted answer = null\n→ answer_hit = 0\n→ continue evaluation\n```\n\nOnly the exact `selected descriptor group has no temporally eligible record`\n`ValueError` is converted. Other exceptions still abort.\n\nThe fresh execution is named DMC-04R2. It reuses evidence seeds 1337–1341\nunder corrected evaluator semantics. Seed 1337 was consumed by the invalid\nDMC-04R execution and is explicitly recorded as a fresh corrected execution,\nnot an unnoticed retry. No model, data, optimizer, threshold, decoder, or\ntraining protocol changes.\n"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DMC04RA_CONTRACT.md").write_text(contract, encoding="utf-8")
    write_json(OUT / "DMC04RA_CONFIG.json", {"unit": "DMC-04R-A", "terminal_state": terminal, "historical_dmc04r_terminal": HISTORICAL_TERMINAL, "historical_dmc04r_commit": HISTORICAL_COMMIT, "fresh_execution_unit": "DMC-04R2", "fresh_execution_required": True, "prior_evidence_seed_consumption": [1337], "fresh_execution_seeds": EVIDENCE_SEEDS, "corrected_rule": evaluator["new"], "unchanged_protocol": protocol, "evidence_training_executed": False, "scientific_accuracy_measured": False})
    write_json(OUT / "historical_dmc04r_identity.json", historical)
    write_json(OUT / "amendment_identity.json", amendment)
    write_json(OUT / "evaluator_semantics.json", evaluator)
    write_json(OUT / "protocol_identity.json", protocol)
    write_json(OUT / "DMC04RA_RECEIPT.json", {"unit": "DMC-04R-A", "terminal_state": terminal, "checks": checks, "fresh_execution_authorized": terminal == "DMC_04RA_FIXED_MISSING_RETRIEVAL_PREREGISTERED", "fresh_execution_unit": "DMC-04R2", "fresh_execution_seeds": EVIDENCE_SEEDS, "evidence_training_executed": False, "scientific_accuracy_measured": False})
    manifest = {str(path.relative_to(OUT)): sha256(path) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    write_json(OUT / "SHA256SUMS.json", manifest)
    print(terminal)
    return 0 if terminal == "DMC_04RA_FIXED_MISSING_RETRIEVAL_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
