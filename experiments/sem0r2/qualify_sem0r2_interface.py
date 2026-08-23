from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEM0R_DIR = Path(__file__).resolve().parents[1] / 'sem0r'
sys.path.insert(0, str(SEM0R_DIR))

from authorize_sem0r import digest, file_sha256, verify_identity  # noqa: E402

LABELS = ['ASSERTED', 'ENTAILED', 'PRESUPPOSED', 'IMPLICATED', 'CONTRADICTED', 'UNKNOWN']
PROBES = [
    'Serialization-only probe A. Return one prediction object for Q1. No benchmark content is present.',
    'Serialization-only probe B. Return one prediction object for Q1. This is not a semantic test.',
    'Serialization-only probe C. Return one prediction object for Q1 using only the required JSON structure.',
]

SYSTEM = (
    'This is a non-scientific interface qualification. Return only the JSON object required by the supplied schema. '
    'Do not add prose or extra keys.'
)


def response_schema() -> dict[str, Any]:
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['predictions'],
        'properties': {
            'predictions': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 1,
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['proposition_id', 'label', 'evidence'],
                    'properties': {
                        'proposition_id': {'type': 'string', 'enum': ['Q1']},
                        'label': {'type': 'string', 'enum': LABELS},
                        'evidence': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True},
                    },
                },
            }
        },
    }


def validate_payload(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != {'predictions'}:
        return ['top_level_shape']
    rows = value.get('predictions')
    if not isinstance(rows, list) or len(rows) != 1:
        return ['prediction_count']
    row = rows[0]
    if not isinstance(row, dict) or set(row) != {'proposition_id', 'label', 'evidence'}:
        return ['prediction_shape']
    if row.get('proposition_id') != 'Q1':
        errors.append('invalid_proposition_id')
    if row.get('label') not in LABELS:
        errors.append('invalid_label')
    ev = row.get('evidence')
    if not isinstance(ev, list) or any(not isinstance(x, str) for x in ev) or len(ev) != len(set(ev)):
        errors.append('invalid_evidence')
    return errors


def call_probe(root: str, model: str, prompt: str, seed: int) -> bytes:
    body = {
        'model': model,
        'stream': False,
        'format': response_schema(),
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': prompt},
        ],
        'options': {'temperature': 0, 'seed': seed, 'num_predict': 128},
    }
    req = urllib.request.Request(
        root.rstrip('/') + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'gri-sem0r2-qualification/1'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=300.0) as resp:
        return resp.read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-identity', type=Path, required=True)
    ap.add_argument('--raw-log', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--ollama-root', default='http://127.0.0.1:11434')
    args = ap.parse_args()

    identity_path = args.model_identity.resolve()
    raw_log = args.raw_log.resolve()
    output = args.output.resolve()
    if raw_log.exists() or output.exists():
        raise FileExistsError('qualification outputs already exist')

    identity = verify_identity(identity_path)
    raw_log.parent.mkdir(parents=True, exist_ok=True)
    probe_results = []

    with raw_log.open('x', encoding='utf-8') as handle:
        for index, prompt in enumerate(PROBES):
            raw = call_probe(args.ollama_root, identity['model_id'], prompt, 20260823 + index)
            raw_sha = hashlib.sha256(raw).hexdigest()
            evidence = {
                'probe': index,
                'response_sha256': raw_sha,
                'response_b64': base64.b64encode(raw).decode('ascii'),
            }
            handle.write(json.dumps(evidence, sort_keys=True) + '\n')
            handle.flush(); os.fsync(handle.fileno())

            outer = json.loads(raw.decode('utf-8'))
            content = outer.get('message', {}).get('content')
            if not isinstance(content, str):
                raise ValueError(f'probe {index}: missing message.content')
            payload = json.loads(content)
            errors = validate_payload(payload)
            if errors:
                raise ValueError(f'probe {index}: invalid structured output: {errors}')
            probe_results.append({'probe': index, 'response_sha256': raw_sha, 'status': 'PASS'})

    record = {
        'schema_version': 1,
        'unit': 'SEM-0R2',
        'status': 'SEM0R2_INTERFACE_QUALIFICATION_PASS',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'scientific_model_calls': 0,
        'interface_model_calls': len(PROBES),
        'semantic_benchmark_content_exposed': False,
        'model_identity_sha256': file_sha256(identity_path),
        'model_identity_record_sha256': identity['identity_record_sha256'],
        'raw_log_sha256': file_sha256(raw_log),
        'probe_results': probe_results,
        'schema_label_enum': LABELS,
    }
    record['qualification_record_sha256'] = digest(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
