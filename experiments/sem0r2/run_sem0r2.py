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

HERE = Path(__file__).resolve().parent
SEM0R_DIR = HERE.parents[0] / 'sem0r'
sys.path.insert(0, str(SEM0R_DIR))

from authorize_sem0r import digest as parent_digest, file_sha256, load_json, verify_identity, verify_manifest  # noqa: E402
from sem0r_contract import LABELS, model_view, validate_prediction_payload  # noqa: E402
from seal_sem0r_predictions import seal_predictions  # noqa: E402
from authorize_sem0r2 import SUCCESSOR_SOURCE_FILES, verify_qualification  # noqa: E402

SYSTEM_PROMPT = '''You are completing a controlled semantic classification experiment.
For every proposition, return exactly one label from: ASSERTED, ENTAILED, PRESUPPOSED, IMPLICATED, CONTRADICTED, UNKNOWN.
Return only JSON with one top-level key "predictions". Each prediction must have exactly: proposition_id, label, evidence.
Evidence must contain only statement IDs from the supplied context that directly support the classification. If the proposition is UNKNOWN and has no supporting statement, use an empty evidence list.
Do not infer a converse from a one-way rule. Preserve genuine ambiguity. Treat cancellable suggestions as IMPLICATED, not ENTAILED.
Do not include explanations or any additional keys.'''


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def response_schema(case: dict[str, Any]) -> dict[str, Any]:
    proposition_ids = [row['id'] for row in case['propositions']]
    evidence_ids = [row['id'] for row in case['context']]
    evidence_items: dict[str, Any] = {'type': 'string'}
    if evidence_ids:
        evidence_items['enum'] = evidence_ids
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['predictions'],
        'properties': {
            'predictions': {
                'type': 'array',
                'minItems': len(proposition_ids),
                'maxItems': len(proposition_ids),
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['proposition_id', 'label', 'evidence'],
                    'properties': {
                        'proposition_id': {'type': 'string', 'enum': proposition_ids},
                        'label': {'type': 'string', 'enum': list(LABELS)},
                        'evidence': {
                            'type': 'array',
                            'items': evidence_items,
                            'uniqueItems': True,
                        },
                    },
                },
            }
        },
    }


def request_raw(*, root: str, model: str, visible_case: dict[str, Any], schema: dict[str, Any], seed: int) -> bytes:
    body = {
        'model': model,
        'stream': False,
        'format': schema,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(visible_case, sort_keys=True, ensure_ascii=False)},
        ],
        'options': {'temperature': 0, 'seed': seed, 'num_predict': 384},
    }
    req = urllib.request.Request(
        root.rstrip('/') + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'gri-sem0r2/1'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=300.0) as resp:
        return resp.read()


def append_raw(handle, *, phase: str, ordinal: int, case_id: str, raw: bytes) -> None:
    row = {
        'phase': phase,
        'ordinal': ordinal,
        'case_id': case_id,
        'response_sha256': hashlib.sha256(raw).hexdigest(),
        'response_b64': base64.b64encode(raw).decode('ascii'),
    }
    handle.write(json.dumps(row, sort_keys=True) + '\n')
    handle.flush(); os.fsync(handle.fileno())


def parse_inner(raw: bytes) -> dict[str, Any]:
    outer = json.loads(raw.decode('utf-8'))
    content = outer.get('message', {}).get('content')
    if not isinstance(content, str):
        raise ValueError('model response missing message.content')
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError('model response JSON is not an object')
    return parsed


def verify_authorization(*, auth_path: Path, manifest_path: Path, identity_path: Path, qualification_path: Path,
                         cases_path: Path, replay_path: Path, ablation_path: Path, baseline_path: Path) -> dict[str, Any]:
    auth = load_json(auth_path)
    if auth.get('status') != 'SEM0R2_ONE_RUN_AUTHORIZED' or auth.get('executions_authorized') != 1 or auth.get('consumed') is not False:
        raise ValueError('SEM-0R2 authorization invalid or already consumed')
    observed = auth.get('authorization_record_sha256')
    body = {k: v for k, v in auth.items() if k != 'authorization_record_sha256'}
    if observed != parent_digest(body):
        raise ValueError('SEM-0R2 authorization digest mismatch')

    manifest = verify_manifest(manifest_path)
    identity = verify_identity(identity_path)
    qualification = verify_qualification(qualification_path, identity_path)
    bindings = auth.get('bindings', {})
    expected = {
        'parent_manifest_sha256': file_sha256(manifest_path),
        'parent_manifest_record_sha256': manifest['manifest_sha256'],
        'model_identity_sha256': file_sha256(identity_path),
        'model_identity_record_sha256': identity['identity_record_sha256'],
        'qualification_sha256': file_sha256(qualification_path),
        'qualification_record_sha256': qualification['qualification_record_sha256'],
        'cases_sha256': file_sha256(cases_path),
        'replay_cases_sha256': file_sha256(replay_path),
        'ablation_cases_sha256': file_sha256(ablation_path),
        'baseline_report_sha256': file_sha256(baseline_path),
    }
    mismatch = {k: {'bound': bindings.get(k), 'observed': v} for k, v in expected.items() if bindings.get(k) != v}
    if mismatch:
        raise ValueError(f'authorization binding mismatch: {mismatch}')

    bound_sources = bindings.get('successor_source_sha256', {})
    source_mismatch = {}
    for name in SUCCESSOR_SOURCE_FILES:
        path = HERE / name
        observed_hash = file_sha256(path) if path.is_file() else None
        if bound_sources.get(name) != observed_hash:
            source_mismatch[name] = {'bound': bound_sources.get(name), 'observed': observed_hash}
    if source_mismatch:
        raise ValueError(f'successor source mismatch: {source_mismatch}')
    return auth


def consume_authorization(path: Path, auth: dict[str, Any], receipt_path: Path) -> None:
    if receipt_path.exists():
        raise FileExistsError(f'run receipt exists: {receipt_path}')
    consumed = dict(auth)
    consumed['consumed'] = True
    consumed['consumed_at'] = datetime.now(timezone.utc).isoformat()
    consumed['status'] = 'SEM0R2_ONE_RUN_CONSUMED'
    consumed.pop('authorization_record_sha256', None)
    consumed['authorization_record_sha256'] = parent_digest(consumed)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(consumed, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(tmp, path)
    receipt = {
        'unit': 'SEM-0R2',
        'status': 'SEM0R2_EXECUTION_STARTED',
        'authorization_sha256_after_consumption': file_sha256(path),
        'started_at': datetime.now(timezone.utc).isoformat(),
        'model_requests_attempted': 0,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def run_phase(*, phase: str, cases: list[dict[str, Any]], predictions_path: Path, raw_log_path: Path,
              seal_path: Path, root: str, model: str, base_seed: int, receipt_path: Path) -> None:
    for path in [predictions_path, raw_log_path, seal_path]:
        if path.exists():
            raise FileExistsError(f'refusing to overwrite: {path}')
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = load_json(receipt_path)

    with predictions_path.open('x', encoding='utf-8') as pred_handle, raw_log_path.open('x', encoding='utf-8') as raw_handle:
        for index, case in enumerate(cases):
            receipt['model_requests_attempted'] = int(receipt.get('model_requests_attempted', 0)) + 1
            receipt['last_phase'] = phase
            receipt['last_case_ordinal'] = index
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')

            case_seed = base_seed + (int(hashlib.sha256(case['id'].encode()).hexdigest()[:8], 16) % 1000000000)
            raw = request_raw(root=root, model=model, visible_case=model_view(case), schema=response_schema(case), seed=case_seed)
            append_raw(raw_handle, phase=phase, ordinal=index, case_id=case['id'], raw=raw)
            parsed = parse_inner(raw)
            errors = validate_prediction_payload(case, parsed)
            if errors:
                raise ValueError(f'{phase} malformed model output at ordinal {index}: {errors}')
            pred_handle.write(json.dumps({'case_id': case['id'], 'payload': parsed}, sort_keys=True) + '\n')
            pred_handle.flush(); os.fsync(pred_handle.fileno())

    seal_predictions(phase, predictions_path, seal_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    for name in [
        'manifest', 'model_identity', 'qualification', 'authorization', 'cases', 'replay_cases', 'ablation_cases', 'baseline_report',
        'live_predictions', 'replay_predictions', 'ablation_predictions', 'live_raw_log', 'replay_raw_log', 'ablation_raw_log',
        'live_seal', 'replay_seal', 'ablation_seal', 'receipt'
    ]:
        ap.add_argument('--' + name.replace('_', '-'), dest=name, type=Path, required=True)
    ap.add_argument('--ollama-root', default='http://127.0.0.1:11434')
    args = ap.parse_args()
    paths = {k: getattr(args, k).resolve() for k in vars(args) if k != 'ollama_root'}

    identity = verify_identity(paths['model_identity'])
    auth = verify_authorization(
        auth_path=paths['authorization'], manifest_path=paths['manifest'], identity_path=paths['model_identity'],
        qualification_path=paths['qualification'], cases_path=paths['cases'], replay_path=paths['replay_cases'],
        ablation_path=paths['ablation_cases'], baseline_path=paths['baseline_report']
    )
    consume_authorization(paths['authorization'], auth, paths['receipt'])

    model = identity['model_id']
    seed = 20260823
    try:
        live_cases = load_jsonl(paths['cases'])
        replay_cases = load_jsonl(paths['replay_cases'])
        ablation_cases = load_jsonl(paths['ablation_cases'])
        run_phase(phase='LIVE', cases=live_cases, predictions_path=paths['live_predictions'], raw_log_path=paths['live_raw_log'], seal_path=paths['live_seal'], root=args.ollama_root, model=model, base_seed=seed, receipt_path=paths['receipt'])
        run_phase(phase='REPLAY', cases=replay_cases, predictions_path=paths['replay_predictions'], raw_log_path=paths['replay_raw_log'], seal_path=paths['replay_seal'], root=args.ollama_root, model=model, base_seed=seed, receipt_path=paths['receipt'])
        run_phase(phase='CONTEXT_ABLATION', cases=ablation_cases, predictions_path=paths['ablation_predictions'], raw_log_path=paths['ablation_raw_log'], seal_path=paths['ablation_seal'], root=args.ollama_root, model=model, base_seed=seed, receipt_path=paths['receipt'])
    except Exception as exc:
        receipt = load_json(paths['receipt'])
        receipt.update({'status': 'SEM0R2_EXECUTION_TERMINATED', 'ended_at': datetime.now(timezone.utc).isoformat(), 'error_type': type(exc).__name__, 'error': str(exc)})
        paths['receipt'].write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        raise

    receipt = load_json(paths['receipt'])
    receipt.update({'status': 'SEM0R2_PREDICTIONS_ALL_SEALED', 'ended_at': datetime.now(timezone.utc).isoformat()})
    paths['receipt'].write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
