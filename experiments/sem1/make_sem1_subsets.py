from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.sem1.build_sem1_instrument import FAMILIES, build_dataset, write_jsonl


def build_subsets() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases, gold = build_dataset()
    by_id = {row["id"]: row for row in cases}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in gold:
        grouped[row["family"]][row["pair_kind"]].append(row)

    replay: list[dict[str, Any]] = []
    ablation: list[dict[str, Any]] = []

    for family_index, family in enumerate(FAMILIES):
        rev = sorted(grouped[family]["REVISION"], key=lambda x: x["id"])
        inv = sorted(grouped[family]["INVARIANCE"], key=lambda x: x["id"])
        if len(rev) != 6 or len(inv) != 6:
            raise AssertionError((family, len(rev), len(inv)))

        if family_index % 2 == 0:
            replay_rows = (rev[0], inv[0], inv[1])
            ablation_rows = (rev[1], rev[2], inv[2])
        else:
            replay_rows = (rev[0], rev[1], inv[0])
            ablation_rows = (rev[2], inv[1], inv[2])

        for meta in replay_rows:
            source = by_id[meta["id"]]
            replay.append(
                {
                    "id": "SEM1-REPLAY-" + source["id"],
                    "source_id": source["id"],
                    "context": source["context"],
                    "propositions": source["propositions"],
                }
            )
        for meta in ablation_rows:
            source = by_id[meta["id"]]
            ablation.append(
                {
                    "id": "SEM1-ABLATE-" + source["id"],
                    "source_id": source["id"],
                    "context": [],
                    "propositions": source["propositions"],
                }
            )

    if len(replay) != 24 or len(ablation) != 24:
        raise AssertionError((len(replay), len(ablation)))
    if {x["source_id"] for x in replay} & {x["source_id"] for x in ablation}:
        raise AssertionError("replay and context-ablation source sets must be disjoint")
    return replay, ablation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--context-ablation", type=Path, required=True)
    args = ap.parse_args()
    replay, ablation = build_subsets()
    write_jsonl(args.replay, replay)
    write_jsonl(args.context_ablation, ablation)
    print(json.dumps({
        "status": "SEM1_SUBSETS_BUILT",
        "replay_count": len(replay),
        "context_ablation_count": len(ablation),
        "overlap": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
