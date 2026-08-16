from pathlib import Path

import pytest

from gri_world0.serialization import write_jsonl
from gri_world0.splits import build_bundle
from gri_world0.validation import ValidationError, validate_artifact_dir


def _write_bundle(path: Path):
    bundle = build_bundle(seed=77, count_per_depth=4, contradiction_count=4)
    files = {"train": bundle.train, "validation": bundle.validation, "test_iid": bundle.test_iid, "contradiction": bundle.contradiction}
    files.update({f"test_depth_{d}": s for d, s in bundle.extrapolation.items()})
    for name, samples in files.items():
        write_jsonl(path / f"{name}.jsonl", samples)


def test_complete_artifact_validates(tmp_path: Path):
    _write_bundle(tmp_path)
    report = validate_artifact_dir(tmp_path)
    assert report["train"]["count"] == 16


def test_missing_artifact_fails_closed(tmp_path: Path):
    _write_bundle(tmp_path)
    (tmp_path / "test_depth_64.jsonl").unlink()
    with pytest.raises(ValidationError):
        validate_artifact_dir(tmp_path)


def test_tampered_answer_fails_closed(tmp_path: Path):
    _write_bundle(tmp_path)
    path = tmp_path / "train.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"answer":"', '"answer":"BROKEN_', 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises((ValidationError, ValueError)):
        validate_artifact_dir(tmp_path)
