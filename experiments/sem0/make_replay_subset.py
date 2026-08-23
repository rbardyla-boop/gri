from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    cases = load_jsonl(args.cases)
    first_pair_by_family = {}
    for case in cases:
        first_pair_by_family.setdefault(case["family"], case["pair_id"])
    replay = [case for case in cases if case["pair_id"] == first_pair_by_family[case["family"]]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in replay), encoding="utf-8")
    print(json.dumps({"replay_case_count": len(replay)}, sort_keys=True))


if __name__ == "__main__":
    main()
