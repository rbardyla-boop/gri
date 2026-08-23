from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

from experiments.sem1.build_sem1_instrument import FAMILIES, LABELS, build_dataset, dataset_summary
from experiments.sem1.make_sem1_subsets import build_subsets

OPAQUE_ID = re.compile(r"^[SP]_[A-F0-9]{12}$")
FORBIDDEN_CASE_KEYS = {"family", "pair_id", "pair_kind", "variant", "renderer", "focus_proposition", "gold"}


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate() -> dict[str, Any]:
    cases, gold = build_dataset()
    cases2, gold2 = build_dataset()
    if cases != cases2 or gold != gold2:
        raise AssertionError("generator is not deterministic")

    if len(cases) != 96 or len(gold) != 96:
        raise AssertionError("case count")
    if len({x["id"] for x in cases}) != 96 or len({x["id"] for x in gold}) != 96:
        raise AssertionError("duplicate case id")
    if [x["id"] for x in cases] != [x["id"] for x in gold]:
        raise AssertionError("case/gold order mismatch")

    by_case = {x["id"]: x for x in cases}
    family_cases: Counter[str] = Counter()
    family_pairs: dict[str, set[str]] = defaultdict(set)
    family_pair_kinds: dict[str, Counter[str]] = defaultdict(Counter)
    family_labels: dict[str, set[str]] = defaultdict(set)
    pair_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case, meta in zip(cases, gold):
        if set(case) & FORBIDDEN_CASE_KEYS:
            raise AssertionError(f"model-visible case leaks metadata: {case['id']}")
        if set(case) != {"id", "context", "propositions"}:
            raise AssertionError(f"unexpected case keys: {case['id']}")
        if len(case["propositions"]) != 6:
            raise AssertionError(f"wrong proposition count: {case['id']}")
        if not case["context"]:
            raise AssertionError(f"empty full context: {case['id']}")

        sids = [x["id"] for x in case["context"]]
        pids = [x["id"] for x in case["propositions"]]
        if len(sids) != len(set(sids)) or len(pids) != len(set(pids)):
            raise AssertionError(f"duplicate opaque id: {case['id']}")
        if not all(OPAQUE_ID.fullmatch(x) for x in sids + pids):
            raise AssertionError(f"nonopaque statement/proposition id: {case['id']}")
        if set(meta["gold"]) != set(pids):
            raise AssertionError(f"gold/proposition mismatch: {case['id']}")
        if meta["focus_proposition"] not in meta["gold"]:
            raise AssertionError(f"focus missing: {case['id']}")

        for item in case["context"]:
            if not isinstance(item["text"], str) or not item["text"].strip():
                raise AssertionError(f"blank context text: {case['id']}")
        for item in case["propositions"]:
            if not isinstance(item["text"], str) or not item["text"].strip():
                raise AssertionError(f"blank proposition text: {case['id']}")

        for pid, answer in meta["gold"].items():
            if answer["label"] not in LABELS:
                raise AssertionError((case["id"], pid, answer["label"]))
            evidence = answer["evidence"]
            if len(evidence) != len(set(evidence)):
                raise AssertionError(f"duplicate gold evidence: {case['id']} {pid}")
            if not set(evidence) <= set(sids):
                raise AssertionError(f"foreign gold evidence: {case['id']} {pid}")
            family_labels[meta["family"]].add(answer["label"])

        family_cases[meta["family"]] += 1
        family_pairs[meta["family"]].add(meta["pair_id"])
        family_pair_kinds[meta["family"]][meta["pair_kind"]] += 1
        pair_rows[meta["pair_id"]].append(meta)

    if set(family_cases) != set(FAMILIES):
        raise AssertionError("family set")
    for family in FAMILIES:
        if family_cases[family] != 12:
            raise AssertionError((family, family_cases[family]))
        if len(family_pairs[family]) != 6:
            raise AssertionError((family, len(family_pairs[family])))
        if family_pair_kinds[family] != Counter({"REVISION": 6, "INVARIANCE": 6}):
            raise AssertionError((family, family_pair_kinds[family]))
        if len(family_labels[family]) < 4:
            raise AssertionError((family, family_labels[family]))

    if len(pair_rows) != 48:
        raise AssertionError("pair count")
    revision_pairs = invariance_pairs = 0
    for pair_id, rows in pair_rows.items():
        if len(rows) != 2 or {x["variant"] for x in rows} != {"A", "B"}:
            raise AssertionError((pair_id, rows))
        if len({x["family"] for x in rows}) != 1 or len({x["pair_kind"] for x in rows}) != 1:
            raise AssertionError(f"pair metadata mismatch: {pair_id}")
        labels = [x["gold"][x["focus_proposition"]]["label"] for x in sorted(rows, key=lambda x: x["variant"])]
        kind = rows[0]["pair_kind"]
        if kind == "REVISION":
            revision_pairs += 1
            if labels[0] == labels[1]:
                raise AssertionError(f"revision focus failed to revise: {pair_id} {labels}")
        elif kind == "INVARIANCE":
            invariance_pairs += 1
            if labels[0] != labels[1]:
                raise AssertionError(f"invariance focus changed: {pair_id} {labels}")
        else:
            raise AssertionError(kind)
    if revision_pairs != 24 or invariance_pairs != 24:
        raise AssertionError((revision_pairs, invariance_pairs))

    summary = dataset_summary(gold)
    if summary["decision_count"] != 576:
        raise AssertionError(summary)
    if summary["one_each_label_cases"] != 0:
        raise AssertionError("one-of-each shortcut returned")
    if summary["unique_label_patterns"] < 10:
        raise AssertionError(f"too few label-cardinality patterns: {summary['unique_label_patterns']}")
    if summary["max_label_pattern_frequency"] > 12:
        raise AssertionError(f"label-cardinality pattern too repetitive: {summary['max_label_pattern_frequency']}")
    if set(summary["global_label_counts"]) != set(LABELS):
        raise AssertionError(f"not all labels represented globally: {summary['global_label_counts']}")

    replay, ablation = build_subsets()
    gold_by_id = {x["id"]: x for x in gold}
    replay_sources = {x["source_id"] for x in replay}
    ablation_sources = {x["source_id"] for x in ablation}
    if len(replay) != 24 or len(ablation) != 24 or replay_sources & ablation_sources:
        raise AssertionError("subset size/overlap")

    for name, subset in (("replay", replay), ("ablation", ablation)):
        fam = Counter(gold_by_id[x["source_id"]]["family"] for x in subset)
        kinds = Counter(gold_by_id[x["source_id"]]["pair_kind"] for x in subset)
        if fam != Counter({family: 3 for family in FAMILIES}):
            raise AssertionError((name, fam))
        if kinds != Counter({"REVISION": 12, "INVARIANCE": 12}):
            raise AssertionError((name, kinds))

    for row in replay:
        source = by_case[row["source_id"]]
        if row["context"] != source["context"] or row["propositions"] != source["propositions"]:
            raise AssertionError(f"replay changed visible content: {row['source_id']}")
    for row in ablation:
        source = by_case[row["source_id"]]
        if row["context"] != [] or row["propositions"] != source["propositions"]:
            raise AssertionError(f"ablation malformed: {row['source_id']}")

    return {
        "status": "SEM1_INSTRUMENT_STRUCTURE_PASS",
        **summary,
        "revision_pairs": revision_pairs,
        "invariance_pairs": invariance_pairs,
        "replay_count": len(replay),
        "context_ablation_count": len(ablation),
        "replay_pair_kinds": {"REVISION": 12, "INVARIANCE": 12},
        "context_ablation_pair_kinds": {"REVISION": 12, "INVARIANCE": 12},
        "case_record_sha256": canonical_sha(cases),
        "gold_record_sha256": canonical_sha(gold),
        "replay_record_sha256": canonical_sha(replay),
        "context_ablation_record_sha256": canonical_sha(ablation),
        "scientific_model_calls": 0,
    }


def main() -> None:
    print(json.dumps(validate(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
