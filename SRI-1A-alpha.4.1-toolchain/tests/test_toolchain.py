import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
V = ROOT / "validate_authorization.py"
PARENT = ROOT.parent / "SRI-1A-alpha.4_LIVE_PILOT_AUTHORIZATION_v0.1.0.zip"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def make_fixture(tmp_path):
    root = Path(tmp_path)
    write(root / "stimulus.bin", b"NON-AUTHORITY stimulus fixture")
    write(root / "scoring.py", "# NON-AUTHORITY scoring fixture\nscore = 0\n")
    write(root / "randomization.json", '{"seed": 7, "branches": ["A", "B"]}\n')
    write(root / "parser.py", """import argparse, json
p=argparse.ArgumentParser(); p.add_argument('--input'); p.add_argument('--output'); a=p.parse_args()
json.dump({'integrity_flags': [], 'rows': []}, open(a.output, 'w'), sort_keys=True, separators=(',', ':'))
""")
    write(root / "schema.json", '{"headers":["id","answer"]}\n')
    write(root / "zero-human.csv", "id,answer\n")
    write(root / "recruitment.json", '{"platform":"NON-AUTHORITY TEST FIXTURE"}\n')
    write(root / "ethics.json", '{"fixture":"NON-AUTHORITY","evidence":"synthetic"}\n')
    write(root / "consent-skeleton.txt", "Purpose. Duration: [DURATION]. Eligibility: [ELIGIBILITY]. Contact: [CONTACT].\n")
    consent_values = {"DURATION": "one minute", "ELIGIBILITY": "test fixture only", "CONTACT": "fixture@example.invalid"}
    rendered = (root / "consent-skeleton.txt").read_text()
    for key, value in consent_values.items():
        rendered = rendered.replace("[" + key + "]", value)
    write(root / "consent.txt", rendered)
    invariant_rows = []
    for name, file_name in (("stimulus", "stimulus.bin"), ("scoring", "scoring.py"), ("randomization", "randomization.json"), ("parser", "parser.py"), ("schema", "schema.json")):
        invariant_rows.append({"name": name, "artifact_path": file_name, "observed_sha256": digest(root / file_name), "trusted_expected_sha256": digest(root / file_name), "upstream_receipt": "NON-AUTHORITY-RECEIPT-" + name, "status": "PASS"})
    write(root / "scientific_invariants.json", json.dumps({"invariants": invariant_rows}, indent=2) + "\n")
    config = {
        "authority": "NON-AUTHORITY", "fixture_authority": "NON-AUTHORITY",
        "recruitment_source": "synthetic", "platform_configuration": "recruitment.json",
        "inclusion_criteria": "fixture", "exclusion_criteria": "none",
        "target_n_or_fixed_stop_rule": "N=0 human rows", "attrition_rule": "frozen",
        "incomplete_response_rule": "recorded", "compensation": "none",
        "data_retention_rule": "delete fixture", "withdrawal_rule": "fixture only",
        "research_contact": "fixture@example.invalid", "ethics_reb_disposition": "APPROVED_WITH_IDENTIFIER",
        "approval_identifier": "NON-AUTHORITY-TEST", "ethics_evidence": "ethics.json",
        "consent_skeleton": "consent-skeleton.txt", "consent": "consent.txt", "consent_values": consent_values,
        "recruitment_config": "recruitment.json", "alpha2_parser": "parser.py", "export_schema": "schema.json",
        "scientific_invariant_manifest": "scientific_invariants.json", "zero_human_export": "zero-human.csv",
        "zero_human_ingestion_receipt": "zero-human-receipt.json"
    }
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    sys.path.insert(0, str(ROOT))
    from zero_human_replay import replay
    replay(root, config, root / "parser.py", root / "schema.json")
    bindings = {
        "operational_config_sha256": digest(root / "operational_config.json"), "consent_sha256": digest(root / "consent.txt"),
        "recruitment_config_sha256": digest(root / "recruitment.json"), "alpha2_parser_sha256": digest(root / "parser.py"),
        "export_schema_sha256": digest(root / "schema.json"), "scientific_invariant_manifest_sha256": digest(root / "scientific_invariants.json"),
        "zero_human_ingestion_receipt_sha256": digest(root / "zero-human-receipt.json"), "ethics_evidence_sha256": digest(root / "ethics.json")
    }
    anchors = {"mode": "NON-AUTHORITY", "alpha4_parent_package_sha256": "fixture-parent", "alpha4_freeze_sha256": "fixture-freeze", "alpha4_manifest_sha256": "fixture-manifest", "bindings": bindings, "validator_source_sha256": digest(V), "scientific_invariants": {}}
    for name, file_name in (("stimulus", "stimulus.bin"), ("scoring", "scoring.py"), ("randomization", "randomization.json"), ("parser", "parser.py"), ("schema", "schema.json")):
        anchors["scientific_invariants"][name] = {"path": file_name, "sha256": digest(root / file_name), "upstream_receipt": "NON-AUTHORITY-RECEIPT-" + name}
    write(root / "TEST_TRUST_ANCHORS.json", json.dumps(anchors, indent=2) + "\n")
    return root


def run(root, *extra):
    return subprocess.run([sys.executable, str(V), "--root", str(root), *extra], capture_output=True, text=True)


def test_successful_synthetic_path_exercises_all_gates(tmp_path):
    root = make_fixture(tmp_path)
    result = run(root, "--test-mode")
    assert result.returncode == 0
    assert result.stdout.strip() == "SRI_ALPHA4_TEST_VALIDATION_PASS"
    assert "SRI_ALPHA4_RECRUITMENT_AUTHORIZED" not in result.stdout
    assert not (root / "SRI_ALPHA4_RECRUITMENT_AUTHORIZATION_RECEIPT.json").exists()


@pytest.mark.parametrize("target,marker", [("parser.py", b"mutated parser"), ("schema.json", b"mutated schema"), ("stimulus.bin", b"mutated stimulus"), ("scoring.py", b"mutated scoring"), ("randomization.json", b"mutated randomization")])
def test_mutated_frozen_or_ingestion_artifact_fails(tmp_path, target, marker):
    root = make_fixture(tmp_path)
    with (root / target).open("ab") as f:
        f.write(marker)
    assert run(root, "--test-mode").returncode in (4, 5)


@pytest.mark.parametrize("field", ["target_n_or_fixed_stop_rule", "compensation", "ethics_reb_disposition"])
def test_unresolved_operational_field_fails(tmp_path, field):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config[field] = "UNRESOLVED"
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    assert run(root, "--test-mode").returncode != 0


def test_arbitrary_hash_and_self_consistent_fake_authority_fail(tmp_path):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config["authority"] = "AUTHORITATIVE"
    config["fixture_authority"] = None
    config["alpha2_parser_sha256"] = "a" * 64
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    result = run(root, "--test-mode")
    assert result.returncode != 0
    assert "SRI_ALPHA4_RECRUITMENT_AUTHORIZED" not in result.stdout


def test_production_ignores_fake_trust_anchor_files(tmp_path):
    if not PARENT.exists():
        pytest.skip("external α.4 parent package not present in standalone toolchain archive")
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config["authority"] = "AUTHORITATIVE"
    config["fixture_authority"] = None
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    fake = json.loads((root / "TEST_TRUST_ANCHORS.json").read_text())
    fake["mode"] = "AUTHORITATIVE"
    write(root / "TRUST_ANCHORS.json", json.dumps(fake) + "\n")
    result = subprocess.run([sys.executable, str(V), "--root", str(root), "--package", str(PARENT)], capture_output=True, text=True)
    assert result.returncode == 4
    assert "SRI_ALPHA4_RECRUITMENT_AUTHORIZED" not in result.stdout


def test_fake_booleans_do_not_help(tmp_path):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config.update({"zero_human_replay": True, "scientific_invariants_unchanged": True})
    config["authority"] = "AUTHORITATIVE"
    config["fixture_authority"] = None
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    assert run(root, "--test-mode").returncode != 0


def test_missing_or_fake_ethics_evidence_fails(tmp_path):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config["ethics_evidence"] = "does-not-exist.json"
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    assert run(root, "--test-mode").returncode != 0


@pytest.mark.parametrize("field", ["alpha2_parser", "export_schema"])
def test_missing_parser_or_schema_fails_closed(tmp_path, field):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config[field] = "missing-frozen-artifact"
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    result = run(root, "--test-mode")
    assert result.returncode != 0


def test_parent_integrity_failure_is_distinct(tmp_path):
    if not PARENT.exists():
        pytest.skip("external α.4 parent package not present in standalone toolchain archive")
    broken = Path(tmp_path) / "broken-parent.zip"
    broken.write_bytes(PARENT.read_bytes() + b"mutation")
    isolated_root = Path(tmp_path) / "validator-root"
    isolated_root.mkdir()
    result = subprocess.run([sys.executable, str(V), "--root", str(isolated_root), "--package", str(broken)], capture_output=True, text=True)
    assert result.returncode == 3
    assert "SRI_ALPHA4_RECRUITMENT_NOT_AUTHORIZED" in result.stdout


def test_consent_placeholder_fails(tmp_path):
    root = make_fixture(tmp_path)
    config = json.loads((root / "operational_config.json").read_text())
    config["consent_values"]["DURATION"] = "UNRESOLVED_DURATION"
    write(root / "operational_config.json", json.dumps(config, indent=2) + "\n")
    assert run(root, "--test-mode").returncode != 0


def test_non_authority_fixture_marker_is_required(tmp_path):
    root = make_fixture(tmp_path)
    anchors = json.loads((root / "TEST_TRUST_ANCHORS.json").read_text())
    anchors["mode"] = "AUTHORITATIVE"
    write(root / "TEST_TRUST_ANCHORS.json", json.dumps(anchors) + "\n")
    assert run(root, "--test-mode").returncode != 0


def test_untouched_parent_remains_locked(tmp_path):
    if not PARENT.exists():
        pytest.skip("external α.4 parent package not present in standalone toolchain archive")
    isolated_root = Path(tmp_path) / "validator-root"
    isolated_root.mkdir()
    result = subprocess.run([sys.executable, str(V), "--root", str(isolated_root), "--package", str(PARENT)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "SRI_ALPHA4_RECRUITMENT_NOT_AUTHORIZED" in result.stdout
