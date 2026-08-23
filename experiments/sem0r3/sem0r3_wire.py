from __future__ import annotations

import json
from typing import Any


def reject_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f'duplicate_json_key:{key}')
        out[key] = value
    return out


def loads_no_duplicates(text: str) -> Any:
    return json.loads(text, object_pairs_hook=reject_duplicate_keys)


def wire_schema(case: dict[str, Any], labels: tuple[str, ...] | list[str]) -> dict[str, Any]:
    pids = [p['id'] for p in case['propositions']]
    eids = [s['id'] for s in case['context']]
    evidence_properties = {eid: {'type': 'boolean'} for eid in eids}
    prediction_properties = {}
    for pid in pids:
        prediction_properties[pid] = {
            'type': 'object',
            'additionalProperties': False,
            'required': ['label', 'evidence'],
            'properties': {
                'label': {'type': 'string', 'enum': list(labels)},
                'evidence': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': evidence_properties,
                },
            },
        }
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['predictions'],
        'properties': {
            'predictions': {
                'type': 'object',
                'additionalProperties': False,
                'required': pids,
                'properties': prediction_properties,
            }
        },
    }


def wire_to_parent(case: dict[str, Any], payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {'predictions'}:
        raise ValueError('wire_top_level_shape')
    predictions = payload.get('predictions')
    if not isinstance(predictions, dict):
        raise ValueError('wire_predictions_not_object')
    pids = [p['id'] for p in case['propositions']]
    if set(predictions) != set(pids):
        raise ValueError('wire_proposition_keys')
    eids = [s['id'] for s in case['context']]
    valid_eids = set(eids)
    rows = []
    for pid in pids:
        row = predictions[pid]
        if not isinstance(row, dict) or set(row) != {'label', 'evidence'}:
            raise ValueError(f'wire_prediction_shape:{pid}')
        ev = row.get('evidence')
        if not isinstance(ev, dict):
            raise ValueError(f'wire_evidence_not_object:{pid}')
        if any(key not in valid_eids for key in ev):
            raise ValueError(f'wire_foreign_evidence:{pid}')
        if any(type(value) is not bool for value in ev.values()):
            raise ValueError(f'wire_evidence_not_boolean:{pid}')
        evidence = [eid for eid in eids if ev.get(eid) is True]
        rows.append({'proposition_id': pid, 'label': row.get('label'), 'evidence': evidence})
    return {'predictions': rows}
