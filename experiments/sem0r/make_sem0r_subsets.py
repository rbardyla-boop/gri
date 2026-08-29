from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def build_subsets(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    replay: list[dict[str, Any]] = []
    ablation: list[dict[str, Any]] = []
    for case in cases:
        suffix = case["pair_id"].rsplit("-", 1)[-1]
        if suffix == "01" and case["variant"] == "A":
            replay.append(case)
        if suffix == "03" and case["variant"] == "B":
            replay.append(case)
        if suffix == "00":
            stripped = dict(case)
            stripped["context"] = []
            stripped["control"] = "CONTEXT_ABLATED_SHORTCUT_PROBE"
            ablation.append(stripped)
    replay.sort(key=lambda x: x["id"])
    ablation.sort(key=lambda x: x["id"])
    if len(replay) != 16:
        raise ValueError(f"expected 16 replay cases, got {len(replay)}")
    if len(ablation) != 16:
        raise ValueError(f"expected 16 ablation cases, got {len(ablation)}")
    return replay, ablation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--ablation", type=Path, required=True)
    args = ap.parse_args()
    replay, ablation = build_subsets(load_jsonl(args.cases))
    write_jsonl(args.replay, replay)
    write_jsonl(args.ablation, ablation)
    print(json.dumps({"replay_cases": len(replay), "ablation_cases": len(ablation)}, sort_keys=True))


if __name__ == "__main__":
    main()
