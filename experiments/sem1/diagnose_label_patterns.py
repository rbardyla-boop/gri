from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from experiments.sem1.build_sem1_instrument import LABELS, build_dataset


def build_report() -> dict[str, Any]:
    _, gold = build_dataset()
    pattern_rows: dict[tuple[int, ...], list[dict[str, Any]]] = defaultdict(list)

    for row in gold:
        local = Counter(answer["label"] for answer in row["gold"].values())
        signature = tuple(local[label] for label in LABELS)
        pattern_rows[signature].append({
            "case_id": row["id"],
            "family": row["family"],
            "pair_id": row["pair_id"],
            "pair_kind": row["pair_kind"],
            "variant": row["variant"],
            "signature": dict(zip(LABELS, signature)),
        })

    ranked = sorted(pattern_rows.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {
        "status": "SEM1_LABEL_PATTERN_DIAGNOSTIC_ONLY",
        "scientific_model_calls": 0,
        "changes_registered_gate": False,
        "label_order": list(LABELS),
        "unique_patterns": len(ranked),
        "max_frequency": max(len(rows) for _, rows in ranked),
        "over_cap": [
            {
                "signature_tuple": list(signature),
                "frequency": len(rows),
                "cases": rows,
            }
            for signature, rows in ranked
            if len(rows) > 12
        ],
        "top_patterns": [
            {
                "signature_tuple": list(signature),
                "frequency": len(rows),
                "family_counts": dict(Counter(r["family"] for r in rows)),
                "pair_kind_counts": dict(Counter(r["pair_kind"] for r in rows)),
            }
            for signature, rows in ranked[:10]
        ],
    }


def main() -> None:
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
