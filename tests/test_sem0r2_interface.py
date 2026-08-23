from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEM0R2 = ROOT / 'experiments' / 'sem0r2'
sys.path.insert(0, str(SEM0R2))

import qualify_sem0r2_interface as qualify
import run_sem0r2 as runner
from authorize_sem0r2 import SUCCESSOR_SOURCE_FILES

EXPECTED_LABELS = {'ASSERTED', 'ENTAILED', 'PRESUPPOSED', 'IMPLICATED', 'CONTRADICTED', 'UNKNOWN'}


def sample_case():
    return {
        'id': 'CASE-X',
        'context': [{'id': 'S1', 'text': 'Alpha.'}, {'id': 'S2', 'text': 'Beta.'}],
        'propositions': [{'id': 'P1', 'text': 'One.'}, {'id': 'P2', 'text': 'Two.'}],
    }


def test_runner_schema_constrains_registered_labels_and_ids():
    schema = runner.response_schema(sample_case())
    item = schema['properties']['predictions']['items']
    assert set(item['properties']['label']['enum']) == EXPECTED_LABELS
    assert set(item['properties']['proposition_id']['enum']) == {'P1', 'P2'}
    assert set(item['properties']['evidence']['items']['enum']) == {'S1', 'S2'}
    assert schema['properties']['predictions']['minItems'] == 2
    assert schema['properties']['predictions']['maxItems'] == 2
    assert item['additionalProperties'] is False


def test_qualification_schema_uses_same_registered_label_enum():
    item = qualify.response_schema()['properties']['predictions']['items']
    assert set(item['properties']['label']['enum']) == EXPECTED_LABELS


def test_no_alias_normalization_is_present():
    text = (SEM0R2 / 'run_sem0r2.py').read_text(encoding='utf-8')
    forbidden = ['IMPLIED', 'casefold(', '.lower()', 'alias_map', 'fuzzy']
    for token in forbidden:
        assert token not in text


def test_raw_response_is_preserved_exactly(tmp_path):
    path = tmp_path / 'raw.jsonl'
    raw = b'{"message":{"content":"sample"},"done":true}\n'
    with path.open('x', encoding='utf-8') as handle:
        runner.append_raw(handle, phase='LIVE', ordinal=2, case_id='CASE-X', raw=raw)
    row = json.loads(path.read_text(encoding='utf-8'))
    assert row['response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(row['response_b64']) == raw
    assert row['ordinal'] == 2


def test_successor_authorization_binds_all_successor_sources():
    assert set(SUCCESSOR_SOURCE_FILES) == {
        'SEM0R2_PROTOCOL.md',
        'qualify_sem0r2_interface.py',
        'authorize_sem0r2.py',
        'run_sem0r2.py',
    }
    for name in SUCCESSOR_SOURCE_FILES:
        assert (SEM0R2 / name).is_file()


def test_protocol_discloses_run001_and_integrity_invalid():
    text = (SEM0R2 / 'SEM0R2_PROTOCOL.md').read_text(encoding='utf-8')
    assert 'RUN-001' in text
    assert 'INTEGRITY_INVALID' in text
    assert 'No label aliases' in text
    assert 'same 72 full-context cases' in text
