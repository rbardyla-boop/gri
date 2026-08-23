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

HERE = Path(__file__).resolve().parent
SEM0R_DIR = HERE.parents[0] / 'sem0r'
sys.path.insert(0, str(SEM0R_DIR))

from authorize_sem0r import digest, file_sha256, verify_identity  # noqa: E402
from sem0r_contract import LABELS  # noqa: E402
from sem0r3_wire import loads_no_duplicates, wire_schema, wire_to_parent  # noqa: E402

CASE = {
    'context': [
        {'id': 'S1', 'text': 'serialization token one'},
        {'id': 'S2', 'text': 'serialization token two'},
        {'id': 'S3', 'text': 'serialization token three'},
    ],
    'propositions': [
        {'id': 'Q1', 'text': 'serialization slot one'},
        {'id': 'Q2', 'text': 'serialization slot two'},
        {'id': 'Q3', 'text': 'serialization slot three'},
    ],
}

TARGETS = [
    {
        'Q1': ('ASSERTED', {'S1': True, 'S2': True}),
        'Q2': ('UNKNOWN', {}),
        'Q3': ('CONTRADICTED', {'S3': True}),
    },
    {
        'Q1': ('ENTAILED', {'S2': True, 'S3': True}),
        'Q2': ('PRESUPPOSED', {'S1': True}),
        'Q3': ('IMPLICATED', {}),
    },
    {
        'Q1': ('UNKNOWN', {'S1': False, 'S2': True}),
        'Q2': ('ASSERTED', {'S1': True, 'S3': True}),
        'Q3': ('ENTAILED', {'S2': False}),
    },
]

SYSTEM = (
    'This is a non-scientific serialization qualification. Follow the requested JSON wire mapping exactly. '
    'There is no semantic task. Return only JSON matching the supplied schema.'
)


def target_wire(target):
    return {
        'predictions': {
            pid: {'label': label, 'evidence': evidence}
            for pid, (label, evidence) in target.items()
        }
    }


def call(root: str, model: str, target, seed: int) -> bytes:
    expected = target_wire(target)
    prompt = 'Emit exactly this serialization mapping, with no semantic interpretation: ' + json.dumps(expected, sort_keys=True)
    body = {
        'model': model,
        'stream': False,
        'format': wire_schema(CASE, LABELS),
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': prompt},
        ],
        'options': {'temperature': 0, 'seed': seed, 'num_predict': 256},
    }
    req = urllib.request.Request(
        root.rstrip('/') + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'gri-sem0r3-qualification/1'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=300.0) as resp:
        return resp.read()


def parse_inner(raw: bytes):
    outer = json.loads(raw.decode('utf-8'))
    content = outer.get('message', {}).get('content')
    if not isinstance(content, str):
        raise ValueError('missing message.content')
    return loads_no_duplicates(content)


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
    results = []

    with raw_log.open('x', encoding='utf-8') as handle:
        for index, target in enumerate(TARGETS):
            raw = call(args.ollama_root, identity['model_id'], target, 20260823 + index)
            sha = hashlib.sha256(raw).hexdigest()
            handle.write(json.dumps({
                'probe': index,
                'response_sha256': sha,
                'response_b64': base64.b64encode(raw).decode('ascii'),
            }, sort_keys=True) + '\n')
            handle.flush(); os.fsync(handle.fileno())

            payload = parse_inner(raw)
            expected = target_wire(target)
            if payload != expected:
                raise ValueError(f'probe {index}: wire output mismatch')
            translated = wire_to_parent(CASE, payload)
            expected_parent = wire_to_parent(CASE, expected)
            if translated != expected_parent:
                raise ValueError(f'probe {index}: translation mismatch')
            results.append({
                'probe': index,
                'response_sha256': sha,
                'translated_sha256': hashlib.sha256(json.dumps(translated, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'status': 'PASS',
            })

    record = {
        'schema_version': 1,
        'unit': 'SEM-0R3',
        'status': 'SEM0R3_INTERFACE_QUALIFICATION_PASS',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'scientific_model_calls': 0,
        'interface_model_calls': len(TARGETS),
        'semantic_benchmark_content_exposed': False,
        'model_identity_sha256': file_sha256(identity_path),
        'model_identity_record_sha256': identity['identity_record_sha256'],
        'raw_log_sha256': file_sha256(raw_log),
        'probe_results': results,
        'wire_form': 'object-keyed-propositions-and-evidence',
    }
    record['qualification_record_sha256'] = digest(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
