from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FILES = (
    "docs/ERC1-MCO04-CLEANROOM-REPRODUCTION.md",
    "experiments/erc1/stage.py",
    "experiments/erc1/compiler.py",
    "experiments/erc1/score.py",
    "experiments/erc1/download_lossless_repack.py",
    "experiments/erc1/run_lossless_repack.sh",
    "tests/test_erc1_cleanroom.py",
    ".github/workflows/erc1-full-reproduction.yml",
)


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
    record = {
        "unit": "ERC-1",
        "status": "ERC1_IMPLEMENTATION_FREEZE_CANDIDATE",
        "freeze_authorized": False,
        "cleanroom_target": "independent reproduction of MCO-04 direct compiler 63/63 scientific service localization",
        "forbidden_implementation_sources": ["scripts/run_mco04.py", "tests/test_mco04.py"],
        "historical_rcaeval_repository_commit": "4695aa69f4f1f57b9094ca04ff235908b73a8e24",
        "historical_hf_revision": "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e",
        "lossless_repack_revision": "92c773ab7bb79f525ec7d5dc53d96a74dbebce4d",
        "expected_total_cases": 90,
        "expected_scientific_cases": 63,
        "scientific_model_calls": 0,
        "full_reproduction_executed": False,
        "source_sha256": hashes,
    }
    record["record_sha256"] = sha256_text(canonical_json(record))
    return record


def verify(repo: Path, freeze: Path) -> dict:
    candidate = build(repo)
    bound = json.loads(freeze.read_text(encoding="utf-8"))
    if bound.get("status") != "ERC1_IMPLEMENTATION_FROZEN" or bound.get("freeze_authorized") is not True:
        raise ValueError("freeze record is not authorized")
    if bound.get("source_sha256") != candidate.get("source_sha256"):
        raise ValueError("frozen source SHA-256 set does not match current source")
    for field in (
        "cleanroom_target",
        "forbidden_implementation_sources",
        "historical_rcaeval_repository_commit",
        "historical_hf_revision",
        "lossless_repack_revision",
        "expected_total_cases",
        "expected_scientific_cases",
    ):
        if bound.get(field) != candidate.get(field):
            raise ValueError(f"freeze binding mismatch: {field}")
    return {"status": "ERC1_IMPLEMENTATION_FREEZE_VERIFIED", "freeze_record_sha256": sha256_file(freeze)}


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
            args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
