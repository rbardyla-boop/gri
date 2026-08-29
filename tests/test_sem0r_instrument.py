from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

SEM0R=Path(__file__).resolve().parents[1]/'experiments'/'sem0r'
if str(SEM0R) not in sys.path:
    sys.path.insert(0,str(SEM0R))

from authorize_sem0r import digest, verify_identity
from generate_sem0r import build_dataset
from make_sem0r_subsets import build_subsets
from run_sem0r import consume_authorization, run_phase, verify_authorization
from score_sem0r import score, verify_seal
from seal_sem0r_predictions import seal_predictions
from sem0r_contract import file_sha256, model_view, validate_prediction_payload
from validate_sem0r_instrument import validate


def write_jsonl(path,rows):
    path.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows),encoding='utf-8')


def gold_payload(case,gold):
    return {'predictions':[{'proposition_id':p['id'],'label':gold[p['id']]['label'],'evidence':gold[p['id']]['evidence']} for p in case['propositions']]}


def unknown_payload(case):
    return {'predictions':[{'proposition_id':p['id'],'label':'UNKNOWN','evidence':[]} for p in case['propositions']]}


def build_scoring_fixture(tmp_path, ablation_oracle=False, replay_mutation=False):
    cases,golds=build_dataset(); replay,ablation=build_subsets(cases); gb={g['id']:g for g in golds}
    paths={name:tmp_path/name for name in ['cases.jsonl','gold.jsonl','replay.jsonl','ablation.jsonl','live.jsonl','rep_pred.jsonl','abl_pred.jsonl','live.seal','rep.seal','abl.seal','baseline.json']}
    write_jsonl(paths['cases.jsonl'],cases); write_jsonl(paths['gold.jsonl'],golds); write_jsonl(paths['replay.jsonl'],replay); write_jsonl(paths['ablation.jsonl'],ablation)
    live=[{'case_id':c['id'],'payload':gold_payload(c,gb[c['id']]['gold'])} for c in cases]
    rep=[{'case_id':c['id'],'payload':gold_payload(c,gb[c['id']]['gold'])} for c in replay]
    if replay_mutation:
        rep[0]['payload']['predictions'][0]['label']='UNKNOWN' if rep[0]['payload']['predictions'][0]['label']!='UNKNOWN' else 'ASSERTED'
    abl=[{'case_id':c['id'],'payload':(gold_payload(c,gb[c['id']]['gold']) if ablation_oracle else unknown_payload(c))} for c in ablation]
    for row in abl:
        for pred in row['payload']['predictions']:
            pred['evidence']=[]
    write_jsonl(paths['live.jsonl'],live); write_jsonl(paths['rep_pred.jsonl'],rep); write_jsonl(paths['abl_pred.jsonl'],abl)
    seal_predictions('LIVE',paths['live.jsonl'],paths['live.seal']); seal_predictions('REPLAY',paths['rep_pred.jsonl'],paths['rep.seal']); seal_predictions('CONTEXT_ABLATION',paths['abl_pred.jsonl'],paths['abl.seal'])
    paths['baseline.json'].write_text(json.dumps({'best_transparent_baseline_macro_f1':0.69251524243837}),encoding='utf-8')
    return paths


def invoke_score(p):
    return score(cases_path=p['cases.jsonl'],replay_cases_path=p['replay.jsonl'],ablation_cases_path=p['ablation.jsonl'],live_predictions_path=p['live.jsonl'],replay_predictions_path=p['rep_pred.jsonl'],ablation_predictions_path=p['abl_pred.jsonl'],live_seal_path=p['live.seal'],replay_seal_path=p['rep.seal'],ablation_seal_path=p['abl.seal'],gold_path=p['gold.jsonl'],baseline_report_path=p['baseline.json'])


def test_01_structure_exact():
    r=validate(); assert r['status']=='PASS'; assert r['case_count']==72; assert r['decision_count']==457; assert r['label_patterns']==47; assert r['max_pattern_frequency']==4


def test_02_pair_counts():
    cases,_=build_dataset(); kinds=Counter()
    for pid in {c['pair_id'] for c in cases}:
        kinds[next(c['pair_kind'] for c in cases if c['pair_id']==pid)]+=1
    assert kinds=={'REVISION':18,'INVARIANCE':18}


def test_03_subsets_exact():
    cases,_=build_dataset(); replay,ablation=build_subsets(cases); assert len(replay)==16; assert len(ablation)==16; assert all(not c['context'] for c in ablation)


def test_04_model_view_hides_metadata():
    cases,_=build_dataset(); view=model_view(cases[0]); assert set(view)=={'context','propositions'}; text=json.dumps(view); assert 'family' not in text and 'renderer' not in text and cases[0]['id'] not in text


def test_05_foreign_evidence_rejected():
    cases,_=build_dataset(); p=unknown_payload(cases[0]); p['predictions'][0]['evidence']=['S_NOT_REAL']; assert any('foreign_evidence' in e for e in validate_prediction_payload(cases[0],p))


def test_06_missing_prediction_rejected():
    cases,_=build_dataset(); p=unknown_payload(cases[0]); p['predictions'].pop(); assert 'missing_predictions' in validate_prediction_payload(cases[0],p)


def test_07_duplicate_prediction_rejected():
    cases,_=build_dataset(); p=unknown_payload(cases[0]); p['predictions'][-1]=dict(p['predictions'][0]); errors=validate_prediction_payload(cases[0],p); assert any('duplicate_proposition' in e for e in errors)


def test_08_identity_tamper_rejected(tmp_path):
    body={'model_id':'llama3.1:8b','artifact_sha256':'a'*64,'runtime':'ollama-0.21.2-openai-compatible','ollama_version':'0.21.2','base_url':'http://127.0.0.1:11434/v1','tag_digest':'b'*64,'selection_basis':'pre-existing','historical_source':{},'checks':{}}
    record=dict(body); record['identity_record_sha256']=digest(body); record['status']='SEM0R_MODEL_PREFLIGHT_PASS'; record['scientific_run_authorized']=False; record['next_gate']='bind'; path=tmp_path/'identity.json'; path.write_text(json.dumps(record)); verify_identity(path); record['model_id']='other'; path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='digest mismatch'):
        verify_identity(path)


def test_09_authorization_tamper_and_second_use_rejected(tmp_path):
    manifest=tmp_path/'manifest'; identity=tmp_path/'identity'; cases=tmp_path/'cases'; replay=tmp_path/'replay'; ablation=tmp_path/'ablation'
    for p,val in [(manifest,'m'),(identity,'i'),(cases,'c'),(replay,'r'),(ablation,'a')]: p.write_text(val)
    auth={'schema_version':1,'unit':'SEM-0R','status':'SEM0R_ONE_RUN_AUTHORIZED','executions_authorized':1,'consumed':False,'bindings':{'instrument_manifest_sha256':file_sha256(manifest),'model_identity_sha256':file_sha256(identity),'cases_sha256':file_sha256(cases),'replay_cases_sha256':file_sha256(replay),'ablation_cases_sha256':file_sha256(ablation)},'prohibitions':{}}
    auth['authorization_record_sha256']=digest(auth); path=tmp_path/'auth.json'; path.write_text(json.dumps(auth))
    verify_authorization(path,manifest,identity,cases,replay,ablation)
    tampered=dict(auth); tampered['bindings']=dict(auth['bindings']); tampered['bindings']['cases_sha256']='0'*64; path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError,match='digest mismatch'):
        verify_authorization(path,manifest,identity,cases,replay,ablation)
    path.write_text(json.dumps(auth)); receipt=tmp_path/'receipt.json'; consume_authorization(path,auth,receipt); consumed=json.loads(path.read_text()); assert consumed['consumed'] is True
    with pytest.raises(FileExistsError):
        consume_authorization(path,consumed,receipt)


def test_10_perfect_live_passes_all_registered_gates(tmp_path):
    p=build_scoring_fixture(tmp_path); r=invoke_score(p); assert r['verdict']=='SEMANTIC_CONTROL_GATE_PASS'; assert all(g['pass'] for g in r['gates'].values())


def test_11_context_free_oracle_fails_dependency_gap(tmp_path):
    p=build_scoring_fixture(tmp_path,ablation_oracle=True); r=invoke_score(p); assert r['gates']['context_dependency_gap']['pass'] is False; assert r['metrics']['context_dependency_gap']==0.0


def test_12_replay_mutation_fails_exact_replay(tmp_path):
    p=build_scoring_fixture(tmp_path,replay_mutation=True); r=invoke_score(p); assert r['gates']['exact_replay_rate']['pass'] is False


def test_13_tampered_prediction_after_seal_rejected(tmp_path):
    p=build_scoring_fixture(tmp_path); p['live.jsonl'].write_text(p['live.jsonl'].read_text()+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='prediction hash mismatch'):
        verify_seal(p['live.seal'],p['live.jsonl'],'LIVE')


def test_14_gold_not_needed_before_seal_verification(tmp_path):
    p=build_scoring_fixture(tmp_path); p['gold.jsonl'].unlink(); p['live.seal'].write_text('{}')
    with pytest.raises(ValueError,match='invalid seal status'):
        invoke_score(p)


def test_15_malformed_output_terminates_without_retry(tmp_path,monkeypatch):
    cases,_=build_dataset(); calls={'n':0}
    def fake(**kwargs): calls['n']+=1; return {'predictions':[]}
    import run_sem0r
    monkeypatch.setattr(run_sem0r,'ollama_chat',fake)
    receipt=tmp_path/'receipt.json'; receipt.write_text(json.dumps({'model_requests_attempted':0}))
    with pytest.raises(ValueError,match='malformed model output'):
        run_phase(phase='LIVE',cases=cases[:1],output_path=tmp_path/'pred.jsonl',root='x',model='m',base_seed=1,receipt_path=receipt)
    assert calls['n']==1
