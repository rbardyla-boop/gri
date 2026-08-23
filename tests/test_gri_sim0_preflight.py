from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "sim" / "gri_sim0.py"
EXPERIMENT = ROOT / "sim" / "experiment_manifest.json"
TEMPLATE_MANIFEST = ROOT / "sim" / "candidate_manifest.example.json"
TEMPLATE_SOURCE = ROOT / "sim" / "candidate_template.py"


def run_sim(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SIM), *args],
        cwd=SIM.parent,
        text=True,
        capture_output=True,
        check=False,
    )


def test_reference_environment_preflight_passes() -> None:
    result = run_sim("validate-experiment", "--experiment", str(EXPERIMENT))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["experiment_id"] == "GRI-02B-REFERENCE-ENVIRONMENT"


def test_unauthorized_candidate_fails_closed() -> None:
    result = run_sim(
        "validate-candidate",
        "--experiment",
        str(EXPERIMENT),
        "--candidate",
        str(TEMPLATE_MANIFEST),
        "--source",
        str(TEMPLATE_SOURCE),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    errors = "\n".join(payload["errors"])
    assert "no implementation authorization" in errors
    assert "source hash mismatch" in errors
    assert "parameter budget missing/exceeded" in errors
    assert "recurrent operation budget missing/exceeded" in errors
    assert "independent accounting audit not PASS" in errors


def test_scaffold_is_explicitly_non_authorizing(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = run_sim("scaffold", "--name", "DEV-SMOKE-ONLY", "--out", str(output))
    assert result.returncode == 0, result.stderr
    assert (output / "candidate.py").is_file()
    assert (output / "candidate_manifest.json").is_file()
    authorization = (output / "AUTHORIZATION_REQUIRED.txt").read_text(encoding="utf-8")
    assert "No candidate mechanism may be implemented or run scientifically" in authorization


def test_missing_canonical_budget_key_fails_closed_without_keyerror(tmp_path: Path) -> None:
    manifest = json.loads(EXPERIMENT.read_text(encoding="utf-8"))
    del manifest["budgets"]["recurrent_plus_query_operations_max"]
    malformed = tmp_path / "malformed-experiment.json"
    malformed.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sim("validate-experiment", "--experiment", str(malformed))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert any("recurrent_plus_query_operations_max" in error for error in payload["errors"])
    assert "KeyError" not in result.stderr


def test_noncanonical_budget_alias_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(EXPERIMENT.read_text(encoding="utf-8"))
    value = manifest["budgets"].pop("recurrent_plus_query_operations_max")
    manifest["budgets"]["recurrent_plus_query"] = value
    malformed = tmp_path / "aliased-experiment.json"
    malformed.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_sim("validate-experiment", "--experiment", str(malformed))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert any("recurrent_plus_query_operations_max" in error for error in payload["errors"])
