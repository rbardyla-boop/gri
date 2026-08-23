from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.forge_e1.generate_te0_e1 import LABELS, make_pool, write_jsonl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--seed-text", required=True)
    args = ap.parse_args()
    if args.count <= 0:
        raise SystemExit("count must be positive")
    rows = make_pool(seed_text=args.seed_text, count=args.count, prefix=args.prefix)
    write_jsonl(args.output, rows)
    print(json.dumps({
        "status": "TE0_E2_POOL_GENERATED",
        "count": len(rows),
        "output": str(args.output),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "seed_sha256": hashlib.sha256(args.seed_text.encode("utf-8")).hexdigest(),
        "label_counts": {label: sum(row["target"]["label"] == label for row in rows) for label in LABELS},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
