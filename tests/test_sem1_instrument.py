from __future__ import annotations

import re
from collections import Counter, defaultdict

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


def test_sem1_invariance_distractors_are_context_counterbalanced() -> None:
    cases, gold = build_dataset()
    case_by = {case["id"]: case for case in cases}
    target_text = {
        "factive_presupposition": "QX2 cracked permanently.",
        "exception_scope": "QX2 is heavy.",
        "nonce_temporal": "QX3 was caused by QX2.",
        "deixis_reference": "The marker is blue.",
        "negation_quantifier": "The seventh QX1 lamp is lit.",
        "invented_lexicon": "QX2 is glass.",
        "abductive_restraint": "QX1 contains iron.",
    }
    observed: dict[tuple[str, int], list[str]] = defaultdict(list)
    scalar: dict[int, list[str]] = defaultdict(list)

    for meta in gold:
        if meta["pair_kind"] != "INVARIANCE":
            continue
        pair_index = int(meta["pair_id"].rsplit("-", 1)[1])
        case = case_by[meta["id"]]
        if meta["family"] == "scalar_scope":
            hits = [p for p in case["propositions"] if p["text"] == "Not all six QX1 trials stabilized."]
            assert len(hits) == 1
            scalar[pair_index].append(meta["gold"][hits[0]["id"]]["label"])
            continue
        text = target_text[meta["family"]]
        hits = [p for p in case["propositions"] if p["text"] == text]
        assert len(hits) == 1
        observed[(meta["family"], pair_index)].append(meta["gold"][hits[0]["id"]]["label"])

    for family in target_text:
        assert observed[(family, 3)] == ["UNKNOWN", "UNKNOWN"]
        assert observed[(family, 4)] == ["ASSERTED", "ASSERTED"]
        assert observed[(family, 5)] == ["CONTRADICTED", "CONTRADICTED"]
    assert scalar[3] == ["IMPLICATED", "IMPLICATED"]
    assert scalar[4] == ["ENTAILED", "ENTAILED"]
    assert scalar[5] == ["CONTRADICTED", "CONTRADICTED"]


def test_sem1_quantifier_revision_distractor_is_context_counterbalanced() -> None:
    cases, gold = build_dataset()
    case_by = {case["id"]: case for case in cases}
    observed: dict[int, list[str]] = defaultdict(list)
    for meta in gold:
        if meta["family"] != "negation_quantifier" or meta["pair_kind"] != "REVISION":
            continue
        pair_index = int(meta["pair_id"].rsplit("-", 1)[1])
        case = case_by[meta["id"]]
        hits = [p for p in case["propositions"] if p["text"] == "The first QX1 lamp is lit."]
        assert len(hits) == 1
        observed[pair_index].append(meta["gold"][hits[0]["id"]]["label"])
    assert observed[0] == ["UNKNOWN", "UNKNOWN"]
    assert observed[1] == ["ASSERTED", "ASSERTED"]
    assert observed[2] == ["CONTRADICTED", "CONTRADICTED"]


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
