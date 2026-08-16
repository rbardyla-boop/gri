from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from . import BENCHMARK_VERSION
from .frames import frames_for_entities
from .schema import SolveStatus
from .serialization import file_sha256, read_jsonl, sample_semantic_id
from .solver import solve
from .splits import EXTRAPOLATION_DEPTHS


class ValidationError(RuntimeError):
    pass


def validate_samples(samples, expected_split: str | None = None) -> dict[str, object]:
    ids: set[str] = set()
    answers = Counter()
    depths = Counter()
    for sample in samples:
        if sample.benchmark_version != BENCHMARK_VERSION:
            raise ValidationError(f"benchmark version mismatch: {sample.benchmark_version}")
        if expected_split and sample.split != expected_split:
            raise ValidationError(f"expected split {expected_split}, got {sample.split}")
        if sample.sample_id != sample_semantic_id(sample):
            raise ValidationError(f"semantic sample hash mismatch: {sample.sample_id}")
        if sample.sample_id in ids:
            raise ValidationError(f"duplicate sample id within split: {sample.sample_id}")
        ids.add(sample.sample_id)

        result = solve(sample.facts, sample.query)
        if sample.contradiction_label:
            if result.status is not SolveStatus.CONTRADICTION:
                raise ValidationError(f"false contradiction label: {sample.sample_id}")
        else:
            if result.status is not SolveStatus.VALID or result.relation is not sample.answer:
                raise ValidationError(f"stored answer mismatch: {sample.sample_id}: {result}")

        answers[sample.answer.value if sample.answer else "NONE"] += 1
        depths[sample.chain_length] += 1

        # Deterministically prove generated frame metadata is valid without
        # changing semantic data.
        for matrix in frames_for_entities(sample.sample_id, 1337, sample.entities).values():
            if not np.allclose(matrix.T @ matrix, np.eye(4), atol=1e-10):
                raise ValidationError(f"non-orthogonal SO(4) frame: {sample.sample_id}")
            if not np.isclose(np.linalg.det(matrix), 1.0, atol=1e-10):
                raise ValidationError(f"improper SO(4) frame: {sample.sample_id}")

    return {
        "count": len(samples),
        "answers": dict(sorted(answers.items())),
        "depths": dict(sorted(depths.items())),
        "ids": ids,
    }


def validate_artifact_dir(path: Path) -> dict[str, object]:
    required = ["train.jsonl", "validation.jsonl", "test_iid.jsonl", "contradiction.jsonl"] + [
        f"test_depth_{d}.jsonl" for d in EXTRAPOLATION_DEPTHS
    ]
    missing = [name for name in required if not (path / name).exists()]
    if missing:
        raise ValidationError(f"missing files: {missing}")

    reports: dict[str, object] = {}
    all_ids: dict[str, str] = {}
    for filename in required:
        split = filename.removesuffix(".jsonl")
        samples = read_jsonl(path / filename)
        report = validate_samples(samples, split)

        if split == "train" and any(s.chain_length > 4 for s in samples):
            raise ValidationError("training split contains chain length > 4")
        if split.startswith("test_depth_"):
            depth = int(split.rsplit("_", 1)[1])
            if any(s.chain_length != depth for s in samples):
                raise ValidationError(f"{split} contains incorrect depth")
        if split == "contradiction" and any(not s.contradiction_label for s in samples):
            raise ValidationError("contradiction split contains ordinary samples")
        if split != "contradiction" and any(s.contradiction_label for s in samples):
            raise ValidationError(f"{split} contains contradiction sample")

        for sid in report["ids"]:  # type: ignore[index]
            if sid in all_ids:
                raise ValidationError(f"cross-split duplicate {sid}: {all_ids[sid]} and {split}")
            all_ids[sid] = split
        report.pop("ids")  # type: ignore[union-attr]
        report["sha256"] = file_sha256(path / filename)  # type: ignore[index]
        reports[split] = report
    return reports
