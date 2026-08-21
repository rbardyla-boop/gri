from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import build_paired_controllers  # noqa: E402


OUT = ROOT / "artifacts/dmc04"
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC03_COMMIT = "489ec45"
DMC04A_COMMIT = "90a30cb"
DMC04P_COMMIT = "61c9ab9"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_manifest(root: Path) -> dict[str, object]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "manifest_available": False, "errors": ["missing manifest"]}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for relative, digest in expected.items():
        path = root / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif sha256(path) != digest:
            errors.append(f"hash:{relative}")
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def identity(name: str, commit: str, artifact_path: str, terminal: str | None = None) -> dict[str, object]:
    path = ROOT / artifact_path
    diff = subprocess.run(["git", "diff", "--exit-code", commit, "--", artifact_path], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    manifest = verify_manifest(path)
    if name == "WORLD-0" and not manifest["manifest_available"]:
        manifest = {"pass": True, "manifest_available": False, "entries": 0, "errors": [], "verification_basis": "frozen_git_commit_boundary"}
    result: dict[str, object] = {"name": name, "expected_commit": commit, "artifact_path": artifact_path, "unchanged_since_expected_commit": diff.returncode == 0, "manifest": manifest}
    if terminal is not None:
        observed = []
        for candidate in sorted(path.glob("*RECEIPT.json")) + sorted(path.glob("*VERDICT.json")):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if "terminal_state" in payload:
                observed.append(payload["terminal_state"])
        result["expected_terminal_state"] = terminal
        result["observed_terminal_states"] = observed
        result["receipt_valid"] = terminal in observed
    result["pass"] = bool(result["unchanged_since_expected_commit"] and result["manifest"]["pass"] and result.get("receipt_valid", True))
    return result


def frozen_identity_check() -> dict[str, object]:
    rows = [
        identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1"),
        identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01", "DMC_01_EXACT_MEMORY_ADVANCES"),
        identity("DMC-03", DMC03_COMMIT, "artifacts/dmc03", "DMC_03_LEARNED_RETENTION_ADVANCES"),
        identity("DMC-04A", DMC04A_COMMIT, "artifacts/dmc04a", "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS"),
        identity("DMC-04P", DMC04P_COMMIT, "artifacts/dmc04p", "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED"),
    ]
    world_output = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    world = rows[0]
    world["validator_terminal"] = world_output.strip().splitlines()[-1] if world_output.strip() else ""
    world["validator_pass"] = world["validator_terminal"] == "GRI_02_WORLD0_PASS"
    world["pass"] = bool(world["pass"] and world["validator_pass"])
    return {"pass": all(row["pass"] for row in rows), "rows": rows}


def frozen_hidden_vectors() -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    for line in (ROOT / "artifacts/dmc04a/datasets/train.jsonl").read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        for memory, record in zip(case["neural_view"]["memory"], case["oracle_view"]["records"]):
            vectors.setdefault(record["answer"], memory["hidden_value"])
    return vectors


def processor_compatibility() -> dict[str, object]:
    vectors = frozen_hidden_vectors()
    rows = []
    for seed in EVIDENCE_SEEDS:
        checkpoint = ROOT / "artifacts/dmc01/checkpoints" / f"exact_seed{seed}_final.pt"
        before = sha256(checkpoint)
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        model, _ = build_paired_controllers(seed)
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        predictions = {}
        correct = 0
        with torch.no_grad():
            for value, vector in vectors.items():
                query = {"kind": "query", "entity": "opaque", "field": "value", "mode": "current", "as_of_episode": None}
                logits = model.answer_query_with_hidden(query, torch.tensor(vector, dtype=torch.float32))
                prediction = VALUES[int(torch.argmax(logits).item())]
                predictions[value] = prediction
                correct += int(prediction == value)
        after = sha256(checkpoint)
        rows.append({"seed": seed, "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256_before": before, "checkpoint_sha256_after": after, "checkpoint_unchanged": before == after, "hidden_value_class_count": len(vectors), "hidden_value_decodes_correctly": correct, "predictions": predictions, "processor_parameters_trainable": sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)})
    return {"pass": all(row["hidden_value_decodes_correctly"] == row["hidden_value_class_count"] and row["checkpoint_unchanged"] and row["processor_parameters_trainable"] == 0 for row in rows), "frozen_hidden_source": json.loads((ROOT / "artifacts/dmc04a/DMC04A_CONFIG.json").read_text(encoding="utf-8"))["frozen_processor"], "rows": rows, "reason_if_failed": "DMC-04A hidden vectors are frozen seed-1337 representations; mandated seed-matched processors 1338-1341 do not decode them consistently."}


def full_tests() -> dict[str, object]:
    result = subprocess.run(["pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"command": "pytest -q", "pass": result.returncode == 0, "returncode": result.returncode, "last_output": result.stdout[-2000:]}


def main() -> int:
    identities = frozen_identity_check()
    tests = full_tests()
    compatibility = processor_compatibility()
    checks = {"full_tests": tests["pass"], "predecessor_identities": identities["pass"], "processor_checkpoint_files_compatible_with_frozen_dmc04a_hidden_values": compatibility["pass"]}
    terminal = "DMC_04_INVALID" if not all(checks.values()) else "DMC_04_PREFLIGHT_PASS"
    payload = {"unit": "DMC-04", "terminal_state": terminal, "checks": checks, "identities": identities, "processor_compatibility": compatibility, "evidence_seeds_executed": [], "evidence_training_executed": False, "scientific_retrieval_accuracy_measured": False, "stop_reason": "The frozen DMC-04A hidden representations are sourced from seed-1337, while the mandated seed-matched processors 1338-1341 cannot decode them; regenerating or replacing them would violate the frozen protocol."}
    write_json(OUT / "DMC04_PREFLIGHT.json", payload)
    write_json(OUT / "SHA256SUMS.json", {"DMC04_PREFLIGHT.json": sha256(OUT / "DMC04_PREFLIGHT.json")})
    print(terminal)
    return 0 if terminal == "DMC_04_PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
