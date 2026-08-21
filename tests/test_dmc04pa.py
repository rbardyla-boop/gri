import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/dmc04pa"


def read_json(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_dmc04pa_structural_receipt_is_advanced_without_evidence() -> None:
    receipt = read_json("DMC04PA_RECEIPT.json")
    assert receipt["terminal_state"] == "DMC_04PA_FIXED_DECODER_PREREGISTERED"
    assert all(receipt["checks"].values())
    assert receipt["evidence_seeds_executed"] == []
    assert receipt["evidence_training_executed"] is False
    assert receipt["scientific_retrieval_accuracy_measured"] is False
    assert receipt["all_hidden_vector_accuracy"] == 1.0
    assert receipt["total_hidden_vectors_checked"] == 4736


def test_dmc04pa_manifest_matches_emitted_files() -> None:
    manifest = read_json("SHA256SUMS.json")
    actual = {}
    for path in sorted(ARTIFACTS.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            actual[str(path.relative_to(ARTIFACTS))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest == actual
