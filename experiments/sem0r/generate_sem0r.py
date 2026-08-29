from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sem0r_gen_core import FAMILIES, LABELS, add_case
from sem0r_families_1 import scalar_pair, presupp_pair
from sem0r_families_2 import release_pair, temporal_pair
from sem0r_families_3 import deixis_pair, quant_pair
from sem0r_families_4 import lexicon_pair, abductive_pair

BUILDERS = [scalar_pair, presupp_pair, release_pair, temporal_pair, deixis_pair, quant_pair, lexicon_pair, abductive_pair]

def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    golds: list[dict[str, Any]] = []
    for family, builder in zip(FAMILIES, BUILDERS):
        pair_count = 6 if family in {"scalar_implicature", "presupposition_trigger"} else 4
        split = pair_count // 2
        for i in range(pair_count):
            invariant = i >= split
            pair_id, pair_kind, left, right = builder(i, invariant)
            for side, item in zip(("A", "B"), (left, right)):
                context, props, focus_index, renderer = item
                cid = f"SEM0R-{family.upper().replace('_','-')}-{i:02d}-{side}"
                add_case(
                    cases,
                    golds,
                    cid=cid,
                    family=family,
                    pair_id=pair_id,
                    pair_kind=pair_kind,
                    variant=side,
                    renderer=renderer,
                    context=context,
                    props=props,
                    focus_index=focus_index,
                )

    if len(cases) != 72 or len(golds) != 72:
        raise AssertionError((len(cases), len(golds)))
    return cases, golds

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    args = ap.parse_args()
    cases, gold = build_dataset()
    write_jsonl(args.cases, cases)
    write_jsonl(args.gold, gold)
    counts = Counter()
    signatures = Counter()
    for row in gold:
        local = Counter(item["label"] for item in row["gold"].values())
        counts.update(local)
        signatures[tuple(local[label] for label in LABELS)] += 1
    print(json.dumps({
        "case_count": len(cases),
        "decision_count": sum(len(c["propositions"]) for c in cases),
        "labels": LABELS,
        "global_label_counts": dict(counts),
        "unique_label_multisets": len(signatures),
        "max_multiset_frequency": max(signatures.values()),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
