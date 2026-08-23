from __future__ import annotations

import json

from experiments.sem1.measurement_adapter import adapt_candidate_output, canonical_semantic_equal
from experiments.sem1.qualify_measurement_adapter import run_qualification


def test_snake_case_evidence_alias_recovers() -> None:
    raw = json.dumps({
        "P1": {"MIR": {"evidence_multiset": ["S2", "S1", "S1"]}},
        "P2": {"label": "UNKNOWN", "evidence": []},
    })
    result = adapt_candidate_output(raw, proposition_ids=("P1", "P2"), statement_ids=("S1", "S2"))
    assert result.status == "RESOLVED"
    assert result.canonical == {
        "P1": {"label": "MIR", "evidence": ["S1", "S2"]},
        "P2": {"label": "UNKNOWN", "evidence": []},
    }


def test_conflicting_redundant_evidence_fails_closed() -> None:
    raw = json.dumps({
        "P1": {"label": "ASSERTED", "evidenceMultiset": [], "evidenceArray": ["S1"]},
        "P2": {"label": "UNKNOWN", "evidence": []},
    })
    result = adapt_candidate_output(raw, proposition_ids=("P1", "P2"), statement_ids=("S1",))
    assert result.status == "UNRESOLVED"
    assert result.code == "CONFLICTING_EVIDENCE_FIELDS"


def test_surrounding_prose_with_one_object_is_allowed() -> None:
    raw = 'Result follows: {"P1":{"label":"ASSERTED","evidence":["S1"]}} End.'
    result = adapt_candidate_output(raw, proposition_ids=("P1",), statement_ids=("S1",))
    assert result.status == "RESOLVED"


def test_two_objects_are_rejected() -> None:
    raw = '{"P1":{"label":"ASSERTED","evidence":["S1"]}} {"x":1}'
    result = adapt_candidate_output(raw, proposition_ids=("P1",), statement_ids=("S1",))
    assert result.status == "UNRESOLVED"
    assert result.code == "JSON_OBJECT_COUNT"


def test_duplicate_json_keys_are_rejected() -> None:
    raw = '{"P1":{"label":"ASSERTED","label":"UNKNOWN","evidence":["S1"]}}'
    result = adapt_candidate_output(raw, proposition_ids=("P1",), statement_ids=("S1",))
    assert result.status == "UNRESOLVED"
    assert result.code == "DUPLICATE_JSON_KEY"


def test_replay_requires_resolved_semantic_equality() -> None:
    a = adapt_candidate_output(
        '{"P1":{"label":"ASSERTED","evidence":["S1","S1"]}}',
        proposition_ids=("P1",),
        statement_ids=("S1",),
    )
    b = adapt_candidate_output(
        'text {"P1":{"label":" asserted ","evidenceArray":["S1"]}} end',
        proposition_ids=("P1",),
        statement_ids=("S1",),
    )
    assert canonical_semantic_equal(a, b)


def test_public_measurement_qualification_is_perfect() -> None:
    report = run_qualification()
    assert report["status"] == "SEM1_MEASUREMENT_QUALIFICATION_PASS"
    assert report["scientific_semantic_content"] is False
    assert report["scientific_model_calls"] == 0
    assert report["positive"]["rate"] == 1.0
    assert report["negative"]["rate"] == 1.0
