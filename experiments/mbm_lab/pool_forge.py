from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write(path: Path, rows):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260823)
    ap.add_argument("--build-frac", type=float, default=0.60)
    ap.add_argument("--dev-frac", type=float, default=0.20)
    args = ap.parse_args()
    if not 0 < args.build_frac < 1 or not 0 < args.dev_frac < 1 or args.build_frac + args.dev_frac >= 1:
        raise ValueError("fractions must leave a non-empty VAULT fraction")
    rows = load(args.fixtures)
    rng = random.Random(args.seed)
    rng.shuffle(rows)
    n = len(rows)
    nb = int(n * args.build_frac)
    nd = int(n * args.dev_frac)
    pools = {
        "BUILD": rows[:nb],
        "DEV": rows[nb:nb + nd],
        "VAULT": rows[nb + nd:],
    }
    hashes = {}
    for name, subset in pools.items():
        path = args.out_dir / f"{name}.jsonl"
        write(path, subset)
        hashes[name] = {"count": len(subset), "sha256": sha256_file(path)}
    manifest = {
        "status": "TE0_POOLS_FROZEN",
        "scientific_content": False,
        "source_fixture_sha256": sha256_file(args.fixtures),
        "seed": args.seed,
        "pools": hashes,
        "policy": {
            "toolsmith_may_read": ["BUILD"],
            "composer_may_read": ["BUILD", "DEV"],
            "grinder_may_read": ["BUILD", "DEV"],
            "judge_only": ["VAULT"],
        },
    }
    path = args.out_dir / "TE0_POOL_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
