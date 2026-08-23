from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.forge.ecology import FailureClass, FailureDiagnosis
from experiments.forge.forge import Case, Forge, Registry, SearchConfig
from experiments.forge.ecology import Composer
from experiments.forge_e1.generate_te0_e1 import make_pool
from experiments.forge_e1.interface_tools import (
    InterfaceRepairToolSmith,
    dedupe_sort_list_field,
    extract_first_json_object,
    normalize_label_field,
    parse_json_object,
    require_exact_keys,
)


def test_pool_generation_is_deterministic_and_disjoint_by_seed() -> None:
    a = make_pool(seed_text="BUILD-seed-v1", count=24, prefix="B")
    b = make_pool(seed_text="BUILD-seed-v1", count=24, prefix="B")
    c = make_pool(seed_text="DEV-seed-v1", count=24, prefix="D")
    assert a == b
    assert a != c
    assert len({row["case_id"] for row in a}) == 24
    assert all(set(row) == {"case_id", "prompt", "target", "template_index"} for row in a)
    assert {row["target"]["label"] for row in a} == {"KAV", "MIR", "TOV"}


def test_extract_json_object_respects_braces_inside_strings() -> None:
    text = 'prefix {"label":"KAV","evidence":["E0001"],"note":"}"} suffix'
    extracted = extract_first_json_object(text)
    assert json.loads(extracted)["note"] == "}"


def test_repair_ops_do_not_invent_unrecognized_label() -> None:
    value = {"label": " kav ", "evidence": ["E2", "E1", "E2"]}
    normalized = normalize_label_field(value, key="label", allowed=["KAV", "MIR", "TOV"])
    assert normalized["label"] == "KAV"
    repaired = dedupe_sort_list_field(normalized, key="evidence")
    assert repaired["evidence"] == ["E1", "E2"]
    with pytest.raises(ValueError, match="LABEL_NOT_RECOVERABLE"):
        normalize_label_field({"label": "UNKNOWN", "evidence": []}, key="label", allowed=["KAV", "MIR", "TOV"])


def test_exact_keys_fails_closed_instead_of_deleting_unknown_fields() -> None:
    with pytest.raises(ValueError, match="UNEXPECTED_OBJECT_KEYS"):
        require_exact_keys({"label": "KAV", "evidence": [], "extra": 1}, keys=["label", "evidence"])


def test_toolsmith_can_discover_multi_step_interface_repair() -> None:
    build = (
        Case("b1", '{"label":"KAV","evidence":["E1"]}', {"label": "KAV", "evidence": ["E1"]}),
        Case("b2", '{"label":"MIR","evidence":["E2"]}', {"label": "MIR", "evidence": ["E2"]}),
        Case("b3", '{"label":"TOV","evidence":["E3"]}', {"label": "TOV", "evidence": ["E3"]}),
    )
    dev = (
        Case("d1", 'answer: {"label":" kav ","evidence":["E2","E1","E2"]}', {"label": "KAV", "evidence": ["E1", "E2"]}),
        Case("d2", '```json\n{"label":"mir","evidence":["E4","E4"]}\n```', {"label": "MIR", "evidence": ["E4"]}),
        Case("d3", '{"label":"TOV","evidence":["E9","E7"]}', {"label": "TOV", "evidence": ["E7", "E9"]}),
    )
    diagnosis = FailureDiagnosis(FailureClass.INTERFACE, ("parse_failure",), "repair")
    smith = InterfaceRepairToolSmith()
    blueprints = smith.propose(diagnosis, build, "text", "json")
    registry = Registry()
    smith.register(registry, blueprints)
    ranked = Composer(Forge(registry)).search(
        dev,
        SearchConfig("text", "json", max_depth=5, max_cost=5, max_candidates=50000),
        complexity_penalty=0.005,
        cost_penalty=0.002,
    )
    assert ranked
    assert ranked[0].dev_score == 1.0
    assert "ts_json_parse_object" in ranked[0].chain.tools
    assert "ts_normalize_label" in ranked[0].chain.tools
    assert "ts_dedupe_sort_evidence" in ranked[0].chain.tools


def test_parse_json_object_rejects_array() -> None:
    with pytest.raises(ValueError, match="JSON_OBJECT_REQUIRED"):
        parse_json_object('[1,2,3]')
