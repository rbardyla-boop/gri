from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from generate_sem0r import build_dataset
from make_sem0r_subsets import build_subsets
from sem0r_contract import THRESHOLDS, canonical, file_sha256
from shortcut_baselines import build_report
from validate_sem0r_instrument import validate

SOURCE_FILES = [
    'sem0r_gen_core.py',
    'sem0r_families_1.py',
    'sem0r_families_2.py',
    'sem0r_families_3.py',
    'sem0r_families_4.py',
    'generate_sem0r.py',
    'make_sem0r_subsets.py',
    'validate_sem0r_instrument.py',
    'sem0r_contract.py',
    'shortcut_baselines.py',
    'preflight_sem0r_model.py',
    'authorize_sem0r.py',
    'seal_sem0r_predictions.py',
    'run_sem0r.py',
    'score_sem0r.py',
    'SEM0R_PREREGISTRATION.md',
]


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, sort_keys=True, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')


def build_freeze_candidate(source_dir: Path, out_dir: Path, manifest_path: Path, freeze: bool=False) -> dict[str, Any]:
    structural=validate()
    cases,gold=build_dataset(); replay,ablation=build_subsets(cases); baseline=build_report()
    out_dir.mkdir(parents=True,exist_ok=True)
    paths={
        'cases':out_dir/'SEM0R_CASES.jsonl',
        'gold':out_dir/'SEM0R_GOLD.jsonl',
        'replay_cases':out_dir/'SEM0R_REPLAY_CASES.jsonl',
        'ablation_cases':out_dir/'SEM0R_CONTEXT_ABLATION_CASES.jsonl',
        'baseline_report':out_dir/'SEM0R_BASELINE_REPORT.json',
    }
    write_jsonl(paths['cases'],cases); write_jsonl(paths['gold'],gold); write_jsonl(paths['replay_cases'],replay); write_jsonl(paths['ablation_cases'],ablation)
    paths['baseline_report'].write_text(json.dumps(baseline,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    source_hashes={}
    for name in SOURCE_FILES:
        path=source_dir/name
        if not path.is_file(): raise FileNotFoundError(f'freeze source missing: {path}')
        source_hashes[name]=file_sha256(path)
    artifacts={key:{'path':str(path),'sha256':file_sha256(path)} for key,path in paths.items()}
    artifacts['cases']['rows']=len(cases); artifacts['gold']['rows']=len(gold); artifacts['replay_cases']['rows']=len(replay); artifacts['ablation_cases']['rows']=len(ablation)
    body={
        'schema_version':1,
        'unit':'SEM-0R',
        'status':'SEM0R_INSTRUMENT_FROZEN' if freeze else 'SEM0R_FREEZE_CANDIDATE',
        'freeze_authorized':bool(freeze),
        'scientific_model_calls_observed_by_builder':0,
        'construct':'semantic_control',
        'structural_validation':structural,
        'thresholds':THRESHOLDS,
        'baseline':{
            'best_shortcut_macro_f1':baseline['best_shortcut_macro_f1'],
            'best_transparent_baseline_macro_f1':baseline['best_transparent_baseline_macro_f1'],
            'effective_macro_f1_floor_from_margin':baseline['best_transparent_baseline_macro_f1'] + THRESHOLDS['shortcut_margin']['value'],
        },
        'model_visible_fields':['context[].id','context[].text','propositions[].id','propositions[].text'],
        'model_hidden_fields':['case id','family','pair_id','pair_kind','variant','renderer','focus_proposition','gold'],
        'source_sha256':source_hashes,
        'generated_artifacts':artifacts,
        'execution_order':['LIVE','SEAL_LIVE','REPLAY','SEAL_REPLAY','CONTEXT_ABLATION','SEAL_CONTEXT_ABLATION','OPEN_GOLD','SCORE_ONCE'],
        'nonclaims':['consciousness','phenomenal experience','personhood','general human-like understanding'],
    }
    body['manifest_sha256']=digest(body)
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    manifest_path.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return body


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source-dir',type=Path,default=Path(__file__).resolve().parent); ap.add_argument('--out-dir',type=Path,required=True); ap.add_argument('--manifest',type=Path,required=True); ap.add_argument('--freeze',action='store_true'); args=ap.parse_args()
    result=build_freeze_candidate(args.source_dir.resolve(),args.out_dir.resolve(),args.manifest.resolve(),freeze=args.freeze)
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__': main()
