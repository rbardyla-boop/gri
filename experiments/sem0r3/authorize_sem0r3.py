from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEM0R_DIR = HERE.parents[0] / 'sem0r'
sys.path.insert(0, str(SEM0R_DIR))

from authorize_sem0r import digest, file_sha256, load_json, verify_identity, verify_manifest  # noqa: E402

PARENT_MANIFEST_RECORD_SHA256 = 'bdbb5f774ec36e444e9bd147cae770554330431aa68b444fb25650cbbcea2d96'
SUCCESSOR_SOURCE_FILES = [
    'SEM0R3_PROTOCOL.md',
    'sem0r3_wire.py',
    'qualify_sem0r3_interface.py',
    'authorize_sem0r3.py',
    'run_sem0r3.py',
]


def verify_qualification(path: Path, identity_path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get('status') != 'SEM0R3_INTERFACE_QUALIFICATION_PASS':
        raise ValueError('interface qualification is not passing')
    observed = value.get('qualification_record_sha256')
    body = {k: v for k, v in value.items() if k != 'qualification_record_sha256'}
    if observed != digest(body):
        raise ValueError('qualification digest mismatch')
    if value.get('model_identity_sha256') != file_sha256(identity_path):
        raise ValueError('qualification/model identity file mismatch')
    if value.get('scientific_model_calls') != 0:
        raise ValueError('qualification record includes scientific calls')
    if value.get('semantic_benchmark_content_exposed') is not False:
        raise ValueError('qualification exposed benchmark content')
    return value


def create_authorization(*, manifest_path: Path, identity_path: Path, qualification_path: Path,
                         cases_path: Path, replay_path: Path, ablation_path: Path,
                         baseline_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f'refusing to overwrite authorization: {output_path}')
    manifest = verify_manifest(manifest_path)
    if manifest.get('manifest_sha256') != PARENT_MANIFEST_RECORD_SHA256:
        raise ValueError('wrong parent frozen manifest record')
    identity = verify_identity(identity_path)
    qualification = verify_qualification(qualification_path, identity_path)

    required = manifest['generated_artifacts']
    observed = {
        'cases_sha256': file_sha256(cases_path),
        'replay_cases_sha256': file_sha256(replay_path),
        'ablation_cases_sha256': file_sha256(ablation_path),
        'baseline_report_sha256': file_sha256(baseline_path),
    }
    expected = {
        'cases_sha256': required['cases']['sha256'],
        'replay_cases_sha256': required['replay_cases']['sha256'],
        'ablation_cases_sha256': required['ablation_cases']['sha256'],
        'baseline_report_sha256': required['baseline_report']['sha256'],
    }
    mismatch = {k: {'expected': expected[k], 'observed': observed[k]} for k in observed if observed[k] != expected[k]}
    if mismatch:
        raise ValueError(f'frozen artifact mismatch: {mismatch}')

    source_hashes = {}
    for name in SUCCESSOR_SOURCE_FILES:
        path = HERE / name
        if not path.is_file():
            raise FileNotFoundError(path)
        source_hashes[name] = file_sha256(path)

    record: dict[str, Any] = {
        'schema_version': 1,
        'unit': 'SEM-0R3',
        'status': 'SEM0R3_ONE_RUN_AUTHORIZED',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'executions_authorized': 1,
        'consumed': False,
        'scientific_scope': 'one complete SEM-0R3 object-keyed interface replication using unchanged SEM-0R semantic content',
        'bindings': {
            'parent_manifest_sha256': file_sha256(manifest_path),
            'parent_manifest_record_sha256': manifest['manifest_sha256'],
            'model_identity_sha256': file_sha256(identity_path),
            'model_identity_record_sha256': identity['identity_record_sha256'],
            'qualification_sha256': file_sha256(qualification_path),
            'qualification_record_sha256': qualification['qualification_record_sha256'],
            **observed,
            'successor_source_sha256': source_hashes,
        },
        'prohibitions': {
            'prior_run_continuation_claim': True,
            'model_substitution': True,
            'semantic_case_change': True,
            'gold_change': True,
            'threshold_change': True,
            'baseline_change': True,
            'label_alias_repair': True,
            'semantic_output_repair': True,
            'per_case_retry': True,
            'scientific_retry_after_consumption': True,
        },
    }
    record['authorization_record_sha256'] = digest(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    for name in ['manifest', 'model_identity', 'qualification', 'cases', 'replay_cases', 'ablation_cases', 'baseline_report', 'output']:
        ap.add_argument('--' + name.replace('_', '-'), dest=name, type=Path, required=True)
    args = ap.parse_args()
    result = create_authorization(
        manifest_path=args.manifest.resolve(),
        identity_path=args.model_identity.resolve(),
        qualification_path=args.qualification.resolve(),
        cases_path=args.cases.resolve(),
        replay_path=args.replay_cases.resolve(),
        ablation_path=args.ablation_cases.resolve(),
        baseline_path=args.baseline_report.resolve(),
        output_path=args.output.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
