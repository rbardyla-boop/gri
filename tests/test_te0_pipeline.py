from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.forge.ecology import Ledger

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "experiments" / "forge" / "fixtures" / "te0_e0"
DEV = "experiments.forge.te0_dev"
AUTH = "experiments.forge.te0_authorize"
JUDGE = "experiments.forge.te0_judge"


def run(module: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def test_development_cli_has_no_vault_argument() -> None:
    p = run(DEV, "--help")
    assert "--vault" not in p.stdout


def test_te0_e0_public_pipeline_qualification() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        champion = t / "champion.json"
        auth = t / "auth.json"
        consumed = t / "consumed.json"
        receipt = t / "receipt.json"
        skill = t / "skill.json"
        ledger = t / "ledger.jsonl"

        run(
            DEV,
            "--build", str(FIX / "build.jsonl"),
            "--dev", str(FIX / "dev.jsonl"),
            "--signals", str(FIX / "signals.json"),
            "--input-kind", "text",
            "--output-kind", "label",
            "--max-depth", "4",
            "--max-cost", "4",
            "--output", str(champion),
            "--ledger", str(ledger),
        )
        manifest = json.loads(champion.read_text())
        assert manifest["authority"] is False
        assert manifest["vault_seen"] is False
        assert manifest["failure_diagnosis"]["class"] == "INTERFACE_FAILURE"
        assert manifest["champion"]["dev_score"] == 1.0
        assert "ts_build_lookup_canonical" in manifest["champion"]["tools"]
        assert "ts_lower" in manifest["champion"]["tools"]
        assert any(x in manifest["champion"]["tools"] for x in ("ts_strip", "ts_normalize_space"))

        run(
            AUTH,
            "--champion", str(champion),
            "--vault", str(FIX / "public_test_vault.jsonl"),
            "--threshold", "1.0",
            "--min-margin-over-null", "0.5",
            "--output", str(auth),
        )

        p = run(
            JUDGE,
            "--champion", str(champion),
            "--vault", str(FIX / "public_test_vault.jsonl"),
            "--authorization", str(auth),
            "--consume-marker", str(consumed),
            "--receipt", str(receipt),
            "--skill-output", str(skill),
            "--ledger", str(ledger),
        )
        outcome = json.loads(p.stdout)
        assert outcome["verdict"] == "PASS"
        assert outcome["score"] == 1.0
        assert outcome["skill_promoted"] is True
        assert consumed.exists() and receipt.exists() and skill.exists()
        assert Ledger(ledger).verify()

        second = run(
            JUDGE,
            "--champion", str(champion),
            "--vault", str(FIX / "public_test_vault.jsonl"),
            "--authorization", str(auth),
            "--consume-marker", str(consumed),
            "--receipt", str(t / "receipt2.json"),
            check=False,
        )
        assert second.returncode != 0
        assert "TE0_VAULT_ALREADY_CONSUMED" in second.stdout


def test_authorization_fails_if_vault_changes_after_binding() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        champion = t / "champion.json"
        auth = t / "auth.json"
        vault = t / "vault.jsonl"
        vault.write_text((FIX / "public_test_vault.jsonl").read_text())

        run(
            DEV,
            "--build", str(FIX / "build.jsonl"),
            "--dev", str(FIX / "dev.jsonl"),
            "--signals", str(FIX / "signals.json"),
            "--input-kind", "text",
            "--output-kind", "label",
            "--output", str(champion),
        )
        run(
            AUTH,
            "--champion", str(champion),
            "--vault", str(vault),
            "--threshold", "1.0",
            "--output", str(auth),
        )
        vault.write_text(vault.read_text() + '{"case_id":"tamper","input":"x","expected":"PASS"}\n')
        p = run(
            JUDGE,
            "--champion", str(champion),
            "--vault", str(vault),
            "--authorization", str(auth),
            "--consume-marker", str(t / "consumed.json"),
            "--receipt", str(t / "receipt.json"),
            check=False,
        )
        assert p.returncode != 0
        assert "Vault binding mismatch" in p.stdout
        assert not (t / "consumed.json").exists()
