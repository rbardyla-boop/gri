from __future__ import annotations

import re
from collections import Counter

from experiments.sem1.build_sem1_instrument import FAMILIES, build_dataset, dataset_summary
from experiments.sem1.make_sem1_subsets import build_subsets
from experiments.sem1.validate_sem1_instrument import validate


FAMILY_NONCE = re.compile(r"\b(?:VEX|RAV|ZEL|NORI|TAL|DAX|EVR|EVS|NER|LUM|TOR|MURK|OBJ|KAV)\d{2}Q\b")


def test_sem1_exact_structure() -> None:
    report = validate()
    assert report["status"] == "SEM1_INSTRUMENT_STRUCTURE_PASS"
    assert report["case_count"] == 96
    assert report["pair_count"] == 48
    assert report["decision_count"] == 576
    assert report["revision_pairs"] == 24
    assert report["invariance_pairs"] == 24
    assert report["replay_count"] == 24
    assert report["context_ablation_count"] == 24
    assert report["one_each_label_cases"] == 0
    assert report["scientific_model_calls"] == 0


def test_sem1_all_families_balanced() -> None:
    _, gold = build_dataset()
    families = Counter(row["family"] for row in gold)
    assert families == Counter({family: 12 for family in FAMILIES})
    for family in FAMILIES:
        local = [row for row in gold if row["family"] == family]
        assert len({row["pair_id"] for row in local}) == 6
        assert Counter(row["pair_kind"] for row in local) == Counter({"REVISION": 6, "INVARIANCE": 6})


def test_sem1_no_metadata_in_case_payload() -> None:
    cases, _ = build_dataset()
    forbidden = {"family", "pair_id", "pair_kind", "variant", "renderer", "focus_proposition", "gold"}
    for case in cases:
        assert set(case) == {"id", "context", "propositions"}
        assert not (set(case) & forbidden)
        assert len(case["propositions"]) == 6


def test_sem1_family_nonce_prefixes_not_model_visible() -> None:
    cases, _ = build_dataset()
    visible = "\n".join(
        item["text"]
        for case in cases
        for section in ("context", "propositions")
        for item in case[section]
    )
    assert not FAMILY_NONCE.search(visible)
    assert "QX1" in visible


def test_sem1_label_pattern_shortcut_not_fixed() -> None:
    _, gold = build_dataset()
    summary = dataset_summary(gold)
    assert summary["one_each_label_cases"] == 0
    assert summary["unique_label_patterns"] >= 10
    assert summary["max_label_pattern_frequency"] <= 12


def test_sem1_subsets_are_balanced_and_disjoint() -> None:
    replay, ablation = build_subsets()
    assert len(replay) == 24
    assert len(ablation) == 24
    assert not ({x["source_id"] for x in replay} & {x["source_id"] for x in ablation})
    assert all(x["context"] for x in replay)
    assert all(x["context"] == [] for x in ablation)
