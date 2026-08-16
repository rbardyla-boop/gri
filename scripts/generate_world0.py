#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_world0.serialization import file_sha256, write_jsonl
from gri_world0.splits import answer_distribution, build_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count-per-depth", type=int, default=32)
    parser.add_argument("--contradiction-count", type=int, default=64)
    args = parser.parse_args()

    bundle = build_bundle(args.seed, args.count_per_depth, args.contradiction_count)
    files = {
        "train": bundle.train,
        "validation": bundle.validation,
        "test_iid": bundle.test_iid,
        "contradiction": bundle.contradiction,
    }
    files.update({f"test_depth_{d}": samples for d, samples in bundle.extrapolation.items()})

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "splits": {}}
    for split, samples in files.items():
        path = args.output / f"{split}.jsonl"
        write_jsonl(path, samples)
        manifest["splits"][split] = {
            "count": len(samples),
            "sha256": file_sha256(path),
            "answer_distribution": answer_distribution(samples),
            "chain_lengths": sorted({s.chain_length for s in samples}),
        }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
