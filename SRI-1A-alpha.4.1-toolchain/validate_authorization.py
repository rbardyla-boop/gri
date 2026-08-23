#!/usr/bin/env python3
"""SRI-1A-α.4.1R fail-closed authorization gate."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from consent_renderer import render_consent
from verify_scientific_invariants import verify as verify_invariants
from zero_human_replay import replay

NOT_AUTHORIZED = 2
PARENT_FAILURE = 3
INVARIANT_FAILURE = 4
REPLAY_FAILURE = 5
ETHICS_FAILURE = 6
PRODUCTION_RECEIPT = "SRI_ALPHA4_RECRUITMENT_AUTHORIZATION_RECEIPT.json"
BLOCKERS = "SRI_ALPHA4_BLOCKERS.json"
PARENT_FILES = {
    "AUTHORIZATION_CHECK.txt", "CONSENT_COMPONENTS_UNRESOLVED.md",
    "DATA_LOCK_PROTOCOL.md", "OPERATIONAL_FREEZE_SHEET.md",
    "PARENT_ALPHA3_EVIDENCE.md", "README.md",
    "SRI-1A-alpha.4_AUTHORIZATION_CONTRACT.json",
    "SRI-1A-alpha.4_FREEZE.json", "SHA256SUMS.json",
    "validate_authorization.py",
}
REQUIRED_FIELDS = (
    "recruitment_source", "platform_configuration", "inclusion_criteria",
    "exclusion_criteria", "target_n_or_fixed_stop_rule", "attrition_rule",
    "incomplete_response_rule", "compensation", "data_retention_rule",
    "withdrawal_rule", "research_contact", "ethics_reb_disposition",
)
BINDINGS = (
    "operational_config_sha256", "consent_sha256",
    "recruitment_config_sha256", "alpha2_parser_sha256",
    "export_schema_sha256", "scientific_invariant_manifest_sha256",
    "zero_human_ingestion_receipt_sha256", "ethics_evidence_sha256",
)


def sha(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unresolved(value):
    return not value or (isinstance(value, str) and "UNRESOLVED" in value)


def local_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def write_failure(root, blockers, checks, code, test_mode=False):
    root.mkdir(parents=True, exist_ok=True)
    (root / PRODUCTION_RECEIPT).unlink(missing_ok=True)
    result = {
        "status": "TEST_VALIDATION_FAIL" if test_mode else "RECRUITMENT_NOT_AUTHORIZED",
        "exit_code": code,
        "blockers": blockers,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validator_result": "FAIL",
    }
    (root / BLOCKERS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("SRI_ALPHA4_TEST_VALIDATION_FAIL" if test_mode else "SRI_ALPHA4_RECRUITMENT_NOT_AUTHORIZED")
    for item in blockers:
        print("- " + item)
    return code


def verify_parent(package, anchors, temp):
    package = Path(package)
    if not package.is_file() or sha(package) != anchors["alpha4_parent_package_sha256"]:
        return None, "parent package SHA-256 mismatch"
    with zipfile.ZipFile(package) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            return None, "parent package has duplicate members"
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts:
                return None, "unsafe parent archive member"
        prefix = Path(names[0]).parts[0] if names and len(Path(names[0]).parts) > 1 else ""
        if not prefix:
            return None, "parent archive has no package root"
        z.extractall(temp)
    dest = temp / prefix
    sums_path = dest / "SHA256SUMS.json"
    if not sums_path.is_file():
        return None, "missing parent SHA256SUMS.json"
    try:
        sums = json.loads(sums_path.read_text(encoding="utf-8"))
    except Exception:
        return None, "unparseable parent SHA256SUMS.json"
    if sums.get("manifest_sha256") != anchors["alpha4_manifest_sha256"]:
        return None, "parent manifest trust anchor mismatch"
    listed = {x.get("name") for x in sums.get("files", []) if isinstance(x, dict)}
    if not listed or not listed.issubset(PARENT_FILES):
        return None, "parent manifest contains unexpected file"
    for item in sums.get("files", []):
        path = dest / item.get("name", "")
        if not path.is_file() or sha(path) != item.get("sha256"):
            return None, "parent file hash mismatch: " + str(item.get("name"))
    actual_names = {Path(name).relative_to(prefix).as_posix() for name in names if name != prefix + "/"}
    if actual_names != PARENT_FILES:
        return None, "parent package has missing or extra frozen files"
    freeze = dest / "SRI-1A-alpha.4_FREEZE.json"
    try:
        freeze_data = json.loads(freeze.read_text(encoding="utf-8"))
    except Exception:
        return None, "unparseable parent freeze"
    if (freeze_data.get("freeze_sha256") != anchors["alpha4_freeze_sha256"] or
            freeze_data.get("manifest_sha256") != anchors["alpha4_manifest_sha256"]):
        return None, "parent freeze trust anchor mismatch"
    return dest, None


def load_anchors(root, test_mode):
    if test_mode:
        path = root / "TEST_TRUST_ANCHORS.json"
        if not path.is_file():
            raise ValueError("missing TEST_TRUST_ANCHORS.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("mode") != "NON-AUTHORITY":
            raise ValueError("test anchor is not NON-AUTHORITY")
        return data
    # Deliberately relative to this verifier, never to operational_config.json.
    return json.loads((Path(__file__).with_name("TRUST_ANCHORS.json")).read_text())


def validate(root: Path, anchors, test_mode=False):
    root = Path(root)
    checks = {}
    blockers = []
    config_path = root / "operational_config.json"
    if not config_path.is_file():
        return write_failure(root, ["missing operational_config.json"], checks, NOT_AUTHORIZED, test_mode)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return write_failure(root, ["unparseable operational_config.json"], checks, NOT_AUTHORIZED, test_mode)
    if not test_mode and config.get("authority") != "AUTHORITATIVE":
        blockers.append("operational configuration is not authoritative")
    if test_mode and config.get("authority") != "NON-AUTHORITY":
        blockers.append("test config must declare NON-AUTHORITY")
    if config.get("fixture_authority") != ("NON-AUTHORITY" if test_mode else None):
        blockers.append("invalid fixture authority marker")
    for key in config:
        if key.endswith("_sha256"):
            blockers.append("config may not supply trust hash: " + key)

    trusted = anchors.get("bindings", {})
    for binding in BINDINGS:
        expected = trusted.get(binding, "UNRESOLVED")
        artifact_key = binding.removesuffix("_sha256")
        artifact = config.get(artifact_key)
        observed = sha(config_path) if binding == "operational_config_sha256" else None
        artifact_path = local_path(root, artifact)
        if binding != "operational_config_sha256" and artifact_path is not None and artifact_path.is_file():
            observed = sha(artifact_path)
        ok = isinstance(expected, str) and len(expected) == 64 and observed == expected
        checks[binding] = {"pass": ok, "trusted_expected": expected, "observed": observed}
        if not ok:
            blockers.append(binding + " unresolved or independently mismatched")
    for field in REQUIRED_FIELDS:
        if unresolved(config.get(field)):
            blockers.append(field + " unresolved")
    if config.get("ethics_reb_disposition") not in (
        "APPROVED_WITH_IDENTIFIER", "DOCUMENTED_NOT_APPLICABLE_WITH_BASIS"
    ):
        blockers.append("ethics_reb_disposition invalid")

    invariant_path = config.get("scientific_invariant_manifest")
    invariant_file = local_path(root, invariant_path)
    if invariant_file is None or not invariant_file.is_file():
        return write_failure(root, blockers + ["scientific invariant manifest missing"], checks, INVARIANT_FAILURE, test_mode)
    try:
        invariant_ok, invariant_results = verify_invariants(root, anchors, invariant_file)
    except Exception as exc:
        invariant_ok, invariant_results = False, [{"error": str(exc)}]
    checks["scientific_invariants"] = {"pass": invariant_ok, "results": invariant_results}
    if not invariant_ok:
        return write_failure(root, blockers + ["scientific invariant verification failed"], checks, INVARIANT_FAILURE, test_mode)

    try:
        skeleton = local_path(root, config.get("consent_skeleton"))
        if skeleton is None:
            raise ValueError("consent skeleton path escapes root")
        rendered = render_consent(skeleton, config.get("consent_values", {}), anchors.get("forbidden_consent_tokens", ()))
        consent_path = local_path(root, config.get("consent"))
        if consent_path is None:
            raise ValueError("consent path escapes root")
        consent_path.write_text(rendered, encoding="utf-8")
        consent_ok = sha(consent_path) == trusted.get("consent_sha256")
    except Exception as exc:
        consent_ok = False
        checks["consent_error"] = str(exc)
        consent_path = root / "consent.final.txt"
    checks["consent"] = {"pass": consent_ok, "observed": sha(consent_path) if consent_path.is_file() else None, "trusted_expected": trusted.get("consent_sha256")}
    if not consent_ok:
        blockers.append("consent rendering/hash gate failed")

    ethics_path = config.get("ethics_evidence") if config.get("ethics_reb_disposition") == "APPROVED_WITH_IDENTIFIER" else config.get("ethics_basis")
    ethics_file = local_path(root, ethics_path)
    ethics_ok = ethics_file is not None and ethics_file.is_file() and sha(ethics_file) == trusted.get("ethics_evidence_sha256")
    if config.get("ethics_reb_disposition") == "APPROVED_WITH_IDENTIFIER":
        ethics_ok = ethics_ok and bool(config.get("approval_identifier"))
    else:
        ethics_ok = ethics_ok and bool(config.get("documented_basis"))
    checks["ethics"] = {"pass": ethics_ok, "observed": sha(ethics_file) if ethics_file is not None and ethics_file.is_file() else None}
    if not ethics_ok:
        return write_failure(root, blockers + ["ethics evidence gate failed"], checks, ETHICS_FAILURE, test_mode)

    try:
        parser = local_path(root, config.get("alpha2_parser"))
        schema = local_path(root, config.get("export_schema"))
        if parser is None or schema is None or not parser.is_file() or not schema.is_file():
            raise ValueError("parser or schema path is missing or escapes root")
        receipt_path = replay(root, config, parser, schema)
        replay_ok = sha(receipt_path) == trusted.get("zero_human_ingestion_receipt_sha256")
    except Exception as exc:
        replay_ok = False
        checks["replay_error"] = str(exc)
        receipt_path = local_path(root, config.get("zero_human_ingestion_receipt", "")) or root / "missing-receipt"
    checks["zero_human_replay"] = {"pass": replay_ok, "observed": sha(receipt_path) if receipt_path.is_file() else None, "trusted_expected": trusted.get("zero_human_ingestion_receipt_sha256")}
    if not replay_ok:
        return write_failure(root, blockers + ["executable zero-human replay failed"], checks, REPLAY_FAILURE, test_mode)
    if blockers:
        return write_failure(root, blockers, checks, NOT_AUTHORIZED, test_mode)
    if test_mode:
        (root / PRODUCTION_RECEIPT).unlink(missing_ok=True)
        print("SRI_ALPHA4_TEST_VALIDATION_PASS")
        return 0
    receipt = {
        "alpha4_parent_package_sha256": anchors["alpha4_parent_package_sha256"],
        "alpha4_freeze_sha256": anchors["alpha4_freeze_sha256"],
        "alpha4_manifest_sha256": anchors["alpha4_manifest_sha256"],
        "operational_config_sha256": sha(config_path),
        "consent_sha256": sha(local_path(root, config["consent"])),
        "recruitment_config_sha256": sha(local_path(root, config["recruitment_config"])),
        "alpha2_parser_sha256": sha(local_path(root, config["alpha2_parser"])),
        "export_schema_sha256": sha(local_path(root, config["export_schema"])),
        "scientific_invariant_manifest_sha256": sha(invariant_file),
        "zero_human_ingestion_receipt_sha256": sha(receipt_path),
        "ethics_evidence_sha256": sha(ethics_file),
        "validator_source_sha256": sha(Path(__file__)),
        "validator_result": "SRI_ALPHA4_RECRUITMENT_AUTHORIZED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    if commit:
        receipt["git_commit"] = commit
    (root / PRODUCTION_RECEIPT).write_bytes(json_bytes(receipt))
    print("SRI_ALPHA4_RECRUITMENT_AUTHORIZED")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        anchors = load_anchors(root, args.test_mode)
    except Exception as exc:
        return write_failure(root, [str(exc)], {}, NOT_AUTHORIZED, args.test_mode)
    if not args.package:
        if args.test_mode:
            return validate(root, anchors, True)
        return write_failure(root, ["parent package is required for independent α.4 integrity verification"], {}, PARENT_FAILURE, False)
    with tempfile.TemporaryDirectory() as directory:
        _, error = verify_parent(args.package, anchors, Path(directory))
        if error:
            return write_failure(root, [error], {}, PARENT_FAILURE, args.test_mode)
    return validate(root, anchors, args.test_mode)


if __name__ == "__main__":
    sys.exit(main())
