from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEM0R = ROOT / 'experiments' / 'sem0r'
SEM0R3 = ROOT / 'experiments' / 'sem0r3'
sys.path.insert(0, str(SEM0R))
sys.path.insert(0, str(SEM0R3))

import pytest  # noqa: E402
from sem0r_contract import LABELS, validate_prediction_payload  # noqa: E402
from sem0r3_wire import loads_no_duplicates, wire_schema, wire_to_parent  # noqa: E402


def case():
    return {
        'context': [
            {'id': 'S1', 'text': 'one'},
            {'id': 'S2', 'text': 'two'},
            {'id': 'S3', 'text': 'three'},
        ],
        'propositions': [
            {'id': 'P1', 'text': 'alpha'},
            {'id': 'P2', 'text': 'beta'},
        ],
    }


def test_schema_keys_predictions_by_proposition():
    schema = wire_schema(case(), LABELS)
    preds = schema['properties']['predictions']
    assert preds['type'] == 'object'
    assert preds['additionalProperties'] is False
    assert preds['required'] == ['P1', 'P2']
    assert set(preds['properties']) == {'P1', 'P2'}


def test_translation_preserves_evidence_set_and_order():
    payload = {
        'predictions': {
            'P2': {'label': 'UNKNOWN', 'evidence': {'S3': False}},
            'P1': {'label': 'ENTAILED', 'evidence': {'S2': True, 'S1': True, 'S3': False}},
        }
    }
    translated = wire_to_parent(case(), payload)
    assert translated == {
        'predictions': [
            {'proposition_id': 'P1', 'label': 'ENTAILED', 'evidence': ['S1', 'S2']},
            {'proposition_id': 'P2', 'label': 'UNKNOWN', 'evidence': []},
        ]
    }
    assert validate_prediction_payload(case(), translated) == []


def test_duplicate_json_key_rejected():
    with pytest.raises(ValueError, match='duplicate_json_key:S1'):
        loads_no_duplicates('{"predictions":{"P1":{"label":"UNKNOWN","evidence":{"S1":true,"S1":true}}}}')


def test_missing_proposition_rejected():
    with pytest.raises(ValueError, match='wire_proposition_keys'):
        wire_to_parent(case(), {'predictions': {'P1': {'label': 'UNKNOWN', 'evidence': {}}}})


def test_foreign_evidence_rejected():
    payload = {
        'predictions': {
            'P1': {'label': 'UNKNOWN', 'evidence': {'S9': True}},
            'P2': {'label': 'UNKNOWN', 'evidence': {}},
        }
    }
    with pytest.raises(ValueError, match='wire_foreign_evidence:P1'):
        wire_to_parent(case(), payload)


def test_non_boolean_evidence_rejected():
    payload = {
        'predictions': {
            'P1': {'label': 'UNKNOWN', 'evidence': {'S1': 1}},
            'P2': {'label': 'UNKNOWN', 'evidence': {}},
        }
    }
    with pytest.raises(ValueError, match='wire_evidence_not_boolean:P1'):
        wire_to_parent(case(), payload)
