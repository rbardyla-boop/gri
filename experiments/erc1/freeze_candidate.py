from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FILES = (
    "docs/ERC1-MCO04-CLEANROOM-REPRODUCTION.md",
    "docs/ERC1B-MCO04-VERIFIED-DATA-BINDING.md",
    "experiments/erc1/stage.py",
    "experiments/erc1/compiler.py",
    "experiments/erc1/score.py",
    "experiments/erc1/download_lossless_repack.py",
    "experiments/erc1/run_lossless_repack.sh",
    "experiments/erc1/freeze_candidate.py",
    "tests/test_erc1_cleanroom.py",
    ".github/workflows/erc1-cleanroom-gate.yml",
    ".github/workflows/erc1-full-reproduction.yml",
)

VERIFIED_DATASET_REVISION = "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e"
QUALIFIED_COMPILER_SHA256 = "2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(repo: Path) -> dict:
    hashes = {}
    for relative in FILES:
        path = repo / relative
        if not path.exists():
            raise FileNotFoundError(relative)
        hashes[relative] = sha256_file(path)

    compiler_sha = hashes["experiments/erc1/compiler.py"]
    if compiler_sha != QUALIFIED_COMPILER_SHA256:
        raise ValueError(
            "ERC-1B compiler changed from qualified ERC-1 implementation: "
            f"{compiler_sha} != {QUALIFIED_COMPILER_SHA256}"
        )

    record = {
        "unit": "ERC-1B",
        "status": "ERC1B_IMPLEMENTATION_FREEZE_CANDIDATE",
        "freeze_authorized": False,
        "cleanroom_target": "independent reproduction of MCO-04 direct compiler 63/63 scientific service localization",
        "predecessor_terminal": "ERC1_DATA_BINDING_INVALID_PRE_PREDICTION",
        "predecessor_scientific_predictions": 0,
        "forbidden_implementation_sources": ["scripts/run_mco04.py", "tests/test_mco04.py"],
        "historical_rcaeval_repository_commit": "4695aa69f4f1f57b9094ca04ff235908b73a8e24",
        "historical_hf_revision": VERIFIED_DATASET_REVISION,
        "verified_dataset_revision": VERIFIED_DATASET_REVISION,
        "qualified_compiler_sha256": QUALIFIED_COMPILER_SHA256,
        "expected_total_cases": 90,
        "expected_scientific_cases": 63,
        "required_scientific_top1_count": 63,
        "required_scientific_top3_count": 63,
        "scientific_model_calls": 0,
        "full_reproduction_executed": False,
        "source_sha256": hashes,
    }
    record["record_sha256"] = sha256_text(canonical_json(record))
    return record


def verify(repo: Path, freeze: Path) -> dict:
    candidate = build(repo)
    bound = json.loads(freeze.read_text(encoding="utf-8"))
    if bound.get("status") != "ERC1B_IMPLEMENTATION_FROZEN" or bound.get("freeze_authorized") is not True:
        raise ValueError("ERC-1B freeze record is not authorized")
    if bound.get("source_sha256") != candidate.get("source_sha256"):
        raise ValueError("frozen source SHA-256 set does not match current source")
    for field in (
        "cleanroom_target",
        "predecessor_terminal",
        "predecessor_scientific_predictions",
        "forbidden_implementation_sources",
        "historical_rcaeval_repository_commit",
        "historical_hf_revision",
        "verified_dataset_revision",
        "qualified_compiler_sha256",
        "expected_total_cases",
        "expected_scientific_cases",
        "required_scientific_top1_count",
        "required_scientific_top3_count",
    ):
        if bound.get(field) != candidate.get(field):
            raise ValueError(f"freeze binding mismatch: {field}")
    return {
        "status": "ERC1B_IMPLEMENTATION_FREEZE_VERIFIED",
        "freeze_record_sha256": sha256_file(freeze),
        "qualified_compiler_sha256": candidate["qualified_compiler_sha256"],
        "verified_dataset_revision": candidate["verified_dataset_revision"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.verify:
        result = verify(repo, args.verify)
    else:
        result = build(repo)
        if args.output:
            args.output.write_text(
                json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
