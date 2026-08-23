from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Any

from experiments.sem1.build_sem1_instrument import LABELS, build_dataset
from experiments.sem1.shortcut_baselines import features, macro_f1


def proposition_only_predictions() -> list[dict[str, Any]]:
    cases, golds = build_dataset()
    meta_by = {g["id"]: g for g in golds}
    pairs = sorted({g["pair_id"] for g in golds})
    rows: list[dict[str, Any]] = []

    for held in pairs:
        class_docs = Counter()
        feat_counts: dict[str, Counter[str]] = {label: Counter() for label in LABELS}
        totals = Counter()
        vocab: set[str] = set()

        for case in cases:
            meta = meta_by[case["id"]]
            if meta["pair_id"] == held:
                continue
            gold = meta["gold"]
            for prop in case["propositions"]:
                label = gold[prop["id"]]["label"]
                f = features(case, prop, with_context=False)
                class_docs[label] += 1
                feat_counts[label].update(f)
                totals[label] += sum(f.values())
                vocab.update(f)

        n_docs = sum(class_docs.values())
        v = max(len(vocab), 1)
        for case in cases:
            meta = meta_by[case["id"]]
            if meta["pair_id"] != held:
                continue
            gold = meta["gold"]
            for prop in case["propositions"]:
                f = features(case, prop, with_context=False)
                scores: dict[str, float] = {}
                for label in LABELS:
                    prior = (class_docs[label] + 1) / (n_docs + len(LABELS))
                    score = math.log(prior)
                    denom = totals[label] + v
                    for feat, count in f.items():
                        score += count * math.log((feat_counts[label][feat] + 1) / denom)
                    scores[label] = score
                pred = max(LABELS, key=lambda label: (scores[label], -LABELS.index(label)))
                rows.append({
                    "case_id": case["id"],
                    "pair_id": meta["pair_id"],
                    "family": meta["family"],
                    "pair_kind": meta["pair_kind"],
                    "variant": meta["variant"],
                    "proposition_id": prop["id"],
                    "text": prop["text"],
                    "gold": gold[prop["id"]]["label"],
                    "pred": pred,
                    "correct": pred == gold[prop["id"]]["label"],
                })
    return rows


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ys = [r["gold"] for r in rows]
    ps = [r["pred"] for r in rows]
    mf1, per = macro_f1(ys, ps)
    return {
        "n": len(rows),
        "accuracy": sum(r["correct"] for r in rows) / len(rows),
        "macro_f1": mf1,
        "per_label_f1": per,
    }


def build_report() -> dict[str, Any]:
    rows = proposition_only_predictions()
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    confusion: Counter[str] = Counter()
    repeated_text: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        by_family[row["family"]].append(row)
        by_pair_kind[row["pair_kind"]].append(row)
        confusion[f"{row['gold']}->{row['pred']}"] += 1
        repeated_text[row["text"]][row["gold"]] += 1

    text_leaks = []
    for text, labels in repeated_text.items():
        total = sum(labels.values())
        if total < 2:
            continue
        majority_label, majority_n = labels.most_common(1)[0]
        purity = majority_n / total
        if purity >= 0.80:
            text_leaks.append({
                "text": text,
                "n": total,
                "label_counts": dict(labels),
                "majority_label": majority_label,
                "purity": purity,
            })
    text_leaks.sort(key=lambda x: (-x["n"], -x["purity"], x["text"]))

    errors_by_family_label: Counter[str] = Counter()
    for row in rows:
        if not row["correct"]:
            errors_by_family_label[f"{row['family']}::{row['gold']}->{row['pred']}"] += 1

    return {
        "status": "SEM1_SHORTCUT_DIAGNOSTIC_ONLY",
        "scientific_model_calls": 0,
        "changes_registered_gate": False,
        "overall": summarize_rows(rows),
        "by_family": {k: summarize_rows(v) for k, v in sorted(by_family.items())},
        "by_pair_kind": {k: summarize_rows(v) for k, v in sorted(by_pair_kind.items())},
        "confusion": dict(confusion.most_common()),
        "top_error_modes": dict(errors_by_family_label.most_common(30)),
        "high_purity_repeated_exact_proposition_text": text_leaks[:50],
    }


def main() -> None:
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
