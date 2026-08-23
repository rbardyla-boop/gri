from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from authorize_sem0r import digest as auth_digest, file_sha256, verify_identity, verify_manifest
from sem0r_contract import model_view, validate_prediction_payload
from seal_sem0r_predictions import seal_predictions

SYSTEM_PROMPT = '''You are completing a controlled semantic classification experiment.
For every proposition, return exactly one label from: ASSERTED, ENTAILED, PRESUPPOSED, IMPLICATED, CONTRADICTED, UNKNOWN.
Return only JSON with one top-level key "predictions". Each prediction must have exactly: proposition_id, label, evidence.
Evidence must contain only statement IDs from the supplied context that directly support the classification. If the proposition is UNKNOWN and has no supporting statement, use an empty evidence list.
Do not infer a converse from a one-way rule. Preserve genuine ambiguity. Treat cancellable suggestions as IMPLICATED, not ENTAILED.
Do not include explanations or any additional keys.'''


def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise ValueError(f'{path} must contain an object')
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def verify_authorization(path: Path, manifest_path: Path, identity_path: Path, cases_path: Path, replay_path: Path, ablation_path: Path) -> dict[str, Any]:
    auth=load_json(path)
    if auth.get('status')!='SEM0R_ONE_RUN_AUTHORIZED': raise ValueError('authorization status invalid')
    if auth.get('executions_authorized')!=1: raise ValueError('authorization count invalid')
    if auth.get('consumed') is not False: raise ValueError('authorization already consumed')
    observed=auth.get('authorization_record_sha256'); body={k:v for k,v in auth.items() if k!='authorization_record_sha256'}
    if observed!=auth_digest(body): raise ValueError('authorization digest mismatch')
    bindings=auth.get('bindings',{})
    expected={
        'instrument_manifest_sha256':file_sha256(manifest_path),
        'model_identity_sha256':file_sha256(identity_path),
        'cases_sha256':file_sha256(cases_path),
        'replay_cases_sha256':file_sha256(replay_path),
        'ablation_cases_sha256':file_sha256(ablation_path),
    }
    mismatch={k:(bindings.get(k),v) for k,v in expected.items() if bindings.get(k)!=v}
    if mismatch: raise ValueError(f'authorization bindings mismatch: {mismatch}')
    return auth


def consume_authorization(path: Path, auth: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    if receipt_path.exists(): raise FileExistsError(f'run receipt exists: {receipt_path}')
    consumed=dict(auth); consumed['consumed']=True; consumed['consumed_at']=datetime.now(timezone.utc).isoformat(); consumed['status']='SEM0R_ONE_RUN_CONSUMED'
    consumed.pop('authorization_record_sha256',None); consumed['authorization_record_sha256']=auth_digest(consumed)
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(consumed,indent=2,sort_keys=True)+'\n',encoding='utf-8'); os.replace(tmp,path)
    receipt={
        'unit':'SEM-0R','status':'SEM0R_EXECUTION_STARTED','authorization_sha256_after_consumption':file_sha256(path),
        'started_at':datetime.now(timezone.utc).isoformat(),'model_requests_attempted':0,
    }
    receipt_path.parent.mkdir(parents=True,exist_ok=True); receipt_path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return receipt


def ollama_chat(*, root: str, model: str, visible_case: dict[str, Any], seed: int, timeout: float=300.0) -> dict[str, Any]:
    body={
        'model':model,
        'stream':False,
        'format':'json',
        'messages':[
            {'role':'system','content':SYSTEM_PROMPT},
            {'role':'user','content':json.dumps(visible_case,sort_keys=True,ensure_ascii=False)},
        ],
        'options':{'temperature':0,'seed':seed,'num_predict':384},
    }
    req=urllib.request.Request(root.rstrip('/')+'/api/chat',data=json.dumps(body).encode('utf-8'),headers={'Content-Type':'application/json','User-Agent':'gri-sem0r/1'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        payload=json.loads(resp.read().decode('utf-8'))
    content=payload.get('message',{}).get('content')
    if not isinstance(content,str): raise ValueError('model response missing message.content')
    parsed=json.loads(content)
    if not isinstance(parsed,dict): raise ValueError('model response JSON is not an object')
    return parsed


def run_phase(*, phase: str, cases: list[dict[str, Any]], output_path: Path, root: str, model: str, base_seed: int, receipt_path: Path) -> None:
    if output_path.exists(): raise FileExistsError(f'refusing to overwrite predictions: {output_path}')
    output_path.parent.mkdir(parents=True,exist_ok=True)
    receipt=load_json(receipt_path)
    with output_path.open('x',encoding='utf-8') as handle:
        for index,case in enumerate(cases):
            receipt['model_requests_attempted']=int(receipt.get('model_requests_attempted',0))+1
            receipt['last_phase']=phase; receipt['last_case_ordinal']=index
            receipt_path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
            case_seed=base_seed + (int(hashlib.sha256(case['id'].encode()).hexdigest()[:8],16) % 1000000000)
            parsed=ollama_chat(root=root,model=model,visible_case=model_view(case),seed=case_seed)
            errors=validate_prediction_payload(case,parsed)
            if errors: raise ValueError(f'{phase} malformed model output at ordinal {index}: {errors}')
            handle.write(json.dumps({'case_id':case['id'],'payload':parsed},sort_keys=True)+'\n'); handle.flush(); os.fsync(handle.fileno())


def main():
    ap=argparse.ArgumentParser()
    for name in ['manifest','model_identity','authorization','cases','replay_cases','ablation_cases','live_predictions','replay_predictions','ablation_predictions','live_seal','replay_seal','ablation_seal','receipt']:
        ap.add_argument('--'+name.replace('_','-'),dest=name,type=Path,required=True)
    ap.add_argument('--ollama-root',default='http://127.0.0.1:11434'); args=ap.parse_args()
    paths={k:getattr(args,k).resolve() for k in vars(args) if k!='ollama_root'}
    verify_manifest(paths['manifest']); identity=verify_identity(paths['model_identity'])
    auth=verify_authorization(paths['authorization'],paths['manifest'],paths['model_identity'],paths['cases'],paths['replay_cases'],paths['ablation_cases'])
    consume_authorization(paths['authorization'],auth,paths['receipt'])
    model=identity['model_id']; seed=20260823
    try:
        live_cases=load_jsonl(paths['cases']); replay_cases=load_jsonl(paths['replay_cases']); ablation_cases=load_jsonl(paths['ablation_cases'])
        run_phase(phase='LIVE',cases=live_cases,output_path=paths['live_predictions'],root=args.ollama_root,model=model,base_seed=seed,receipt_path=paths['receipt'])
        seal_predictions('LIVE',paths['live_predictions'],paths['live_seal'])
        run_phase(phase='REPLAY',cases=replay_cases,output_path=paths['replay_predictions'],root=args.ollama_root,model=model,base_seed=seed,receipt_path=paths['receipt'])
        seal_predictions('REPLAY',paths['replay_predictions'],paths['replay_seal'])
        run_phase(phase='CONTEXT_ABLATION',cases=ablation_cases,output_path=paths['ablation_predictions'],root=args.ollama_root,model=model,base_seed=seed,receipt_path=paths['receipt'])
        seal_predictions('CONTEXT_ABLATION',paths['ablation_predictions'],paths['ablation_seal'])
    except Exception as exc:
        r=load_json(paths['receipt']); r.update({'status':'SEM0R_EXECUTION_TERMINATED','ended_at':datetime.now(timezone.utc).isoformat(),'error_type':type(exc).__name__,'error':str(exc)}); paths['receipt'].write_text(json.dumps(r,indent=2,sort_keys=True)+'\n',encoding='utf-8'); raise
    r=load_json(paths['receipt']); r.update({'status':'SEM0R_PREDICTIONS_ALL_SEALED','ended_at':datetime.now(timezone.utc).isoformat()}); paths['receipt'].write_text(json.dumps(r,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(r,indent=2,sort_keys=True))

if __name__=='__main__': main()
