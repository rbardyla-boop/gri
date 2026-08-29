from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sem0r_contract import LABELS, THRESHOLDS, canonical, file_sha256, payload_index, validate_prediction_payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def verify_seal(seal_path: Path, predictions_path: Path, expected_phase: str) -> dict[str, Any]:
    seal = json.loads(seal_path.read_text(encoding='utf-8'))
    if seal.get('status') != 'SEM0R_PREDICTIONS_SEALED':
        raise ValueError(f'{expected_phase}: invalid seal status')
    if seal.get('phase') != expected_phase:
        raise ValueError(f'{expected_phase}: wrong seal phase')
    observed = file_sha256(predictions_path)
    if seal.get('predictions_sha256') != observed:
        raise ValueError(f'{expected_phase}: prediction hash mismatch')
    return seal


def load_prediction_map(path: Path, cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(path)
    expected = {c['id']: c for c in cases}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'case_id', 'payload'}:
            raise ValueError(f'{path}: malformed prediction row')
        cid = row.get('case_id')
        if cid not in expected:
            raise ValueError(f'{path}: unknown case {cid}')
        if cid in out:
            raise ValueError(f'{path}: duplicate case {cid}')
        errors = validate_prediction_payload(expected[cid], row.get('payload'))
        if errors:
            raise ValueError(f'{path}: invalid payload for {cid}: {errors}')
        out[cid] = row['payload']
    if set(out) != set(expected):
        missing = sorted(set(expected) - set(out))
        raise ValueError(f'{path}: missing cases {missing[:5]}')
    return out


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    scores=[]
    for label in LABELS:
        tp=sum(a==label and b==label for a,b in zip(y_true,y_pred))
        fp=sum(a!=label and b==label for a,b in zip(y_true,y_pred))
        fn=sum(a==label and b!=label for a,b in zip(y_true,y_pred))
        precision=tp/(tp+fp) if tp+fp else 0.0
        recall=tp/(tp+fn) if tp+fn else 0.0
        scores.append(2*precision*recall/(precision+recall) if precision+recall else 0.0)
    return sum(scores)/len(scores)


def accuracy_for(case_ids: set[str], cases_by_id: dict[str, dict[str, Any]], gold_by_id: dict[str, dict[str, Any]], pred_by_id: dict[str, dict[str, Any]]) -> float:
    good=total=0
    for cid in sorted(case_ids):
        pred=payload_index(pred_by_id[cid]); gold=gold_by_id[cid]['gold']
        for prop in cases_by_id[cid]['propositions']:
            pid=prop['id']; total+=1; good += pred[pid]['label']==gold[pid]['label']
    return good/total if total else 0.0


def gate_pass(value: float | int, spec: dict[str, Any]) -> bool:
    op=spec['op']; target=spec['value']
    if op == '>=': return value >= target
    if op == '<=': return value <= target
    if op == '=': return value == target
    raise ValueError(op)


def score(*, cases_path: Path, replay_cases_path: Path, ablation_cases_path: Path,
          live_predictions_path: Path, replay_predictions_path: Path, ablation_predictions_path: Path,
          live_seal_path: Path, replay_seal_path: Path, ablation_seal_path: Path,
          gold_path: Path, baseline_report_path: Path) -> dict[str, Any]:
    cases=load_jsonl(cases_path); replay_cases=load_jsonl(replay_cases_path); ablation_cases=load_jsonl(ablation_cases_path)
    verify_seal(live_seal_path, live_predictions_path, 'LIVE')
    verify_seal(replay_seal_path, replay_predictions_path, 'REPLAY')
    verify_seal(ablation_seal_path, ablation_predictions_path, 'CONTEXT_ABLATION')
    live=load_prediction_map(live_predictions_path,cases)
    replay=load_prediction_map(replay_predictions_path,replay_cases)
    ablation=load_prediction_map(ablation_predictions_path,ablation_cases)
    # First gold read occurs here, after all seals and prediction integrity checks.
    gold_rows=load_jsonl(gold_path)
    baseline=json.loads(baseline_report_path.read_text(encoding='utf-8'))
    best_baseline=float(baseline['best_transparent_baseline_macro_f1'])

    cases_by={c['id']:c for c in cases}; gold_by={g['id']:g for g in gold_rows}
    if set(cases_by)!=set(gold_by): raise ValueError('gold/case id mismatch')
    ys=[]; ps=[]; family_good=Counter(); family_total=Counter(); unknown_total=unknown_over=0
    gold_edges:set[tuple[str,str,str]]=set(); pred_edges:set[tuple[str,str,str]]=set()
    for cid,case in cases_by.items():
        pred=payload_index(live[cid]); gold=gold_by[cid]['gold']
        for prop in case['propositions']:
            pid=prop['id']; g=gold[pid]['label']; p=pred[pid]['label']; ys.append(g); ps.append(p)
            family_total[case['family']]+=1; family_good[case['family']]+=g==p
            if g=='UNKNOWN': unknown_total+=1; unknown_over += p!='UNKNOWN'
            for eid in gold[pid]['evidence']: gold_edges.add((cid,pid,eid))
            for eid in pred[pid]['evidence']: pred_edges.add((cid,pid,eid))
    accuracy=sum(a==b for a,b in zip(ys,ps))/len(ys)
    mf1=macro_f1(ys,ps)
    tp=len(gold_edges & pred_edges); fp=len(pred_edges-gold_edges); fn=len(gold_edges-pred_edges)
    ep=tp/(tp+fp) if tp+fp else 0.0; er=tp/(tp+fn) if tp+fn else 0.0
    evidence_f1=2*ep*er/(ep+er) if ep+er else 0.0
    fam_acc={f:family_good[f]/family_total[f] for f in family_total}

    pairs=defaultdict(list)
    for case in cases: pairs[case['pair_id']].append(case)
    revision_good=invariance_good=revision_n=invariance_n=0
    for rows in pairs.values():
        rows=sorted(rows,key=lambda x:x['variant']); kind=rows[0]['pair_kind']
        exact=[]; predicted_labels=[]
        for row in rows:
            pid=row['focus_proposition']; pred=payload_index(live[row['id']])[pid]['label']; gold=gold_by[row['id']]['gold'][pid]['label']
            exact.append(pred==gold); predicted_labels.append(pred)
        relation=(predicted_labels[0]!=predicted_labels[1]) if kind=='REVISION' else (predicted_labels[0]==predicted_labels[1])
        passed=all(exact) and relation
        if kind=='REVISION': revision_n+=1; revision_good+=passed
        else: invariance_n+=1; invariance_good+=passed

    def normalized_payload(payload):
        rows=[]
        for row in payload['predictions']:
            rows.append({'proposition_id':row['proposition_id'],'label':row['label'],'evidence':sorted(row['evidence'])})
        return {'predictions':sorted(rows,key=lambda x:x['proposition_id'])}
    replay_exact=sum(canonical(normalized_payload(live[cid]))==canonical(normalized_payload(replay[cid])) for cid in replay)/len(replay)
    ablation_ids=set(ablation)
    full_matched=accuracy_for(ablation_ids,cases_by,gold_by,live)
    ablation_acc=accuracy_for(ablation_ids,{c['id']:c for c in ablation_cases},gold_by,ablation)
    context_gap=full_matched-ablation_acc
    nonce_ids={c['id'] for c in cases if c['family'] in {'nonce_temporal','invented_lexicon','abductive_trap'}}
    nonce_acc=accuracy_for(nonce_ids,cases_by,gold_by,live)
    abductive_rows=[c for c in cases if c['family']=='abductive_trap']
    abductive_good=0
    for c in abductive_rows:
        pid=c['focus_proposition']; abductive_good += payload_index(live[c['id']])[pid]['label']==gold_by[c['id']]['gold'][pid]['label']
    abductive_acc=abductive_good/len(abductive_rows)

    metrics={
        'accuracy':accuracy,
        'macro_f1':mf1,
        'revision_pair_accuracy':revision_good/revision_n,
        'invariance_pair_accuracy':invariance_good/invariance_n,
        'unknown_overclaim_rate':unknown_over/unknown_total,
        'evidence_dependency_f1':evidence_f1,
        'nonce_world_accuracy':nonce_acc,
        'worst_family_accuracy':min(fam_acc.values()),
        'scalar_pragmatics_accuracy':fam_acc['scalar_implicature'],
        'presupposition_accuracy':fam_acc['presupposition_trigger'],
        'abductive_restraint_accuracy':abductive_acc,
        'shortcut_margin':mf1-best_baseline,
        'context_dependency_gap':context_gap,
        'exact_replay_rate':replay_exact,
        'integrity_errors':0,
    }
    gates={name:{'value':metrics[name],'threshold':spec,'pass':gate_pass(metrics[name],spec)} for name,spec in THRESHOLDS.items()}
    all_pass=all(g['pass'] for g in gates.values())
    return {
        'unit':'SEM-0R',
        'construct':'semantic_control',
        'verdict':'SEMANTIC_CONTROL_GATE_PASS' if all_pass else 'SEMANTIC_CONTROL_GATE_FAIL',
        'metrics':metrics,
        'gates':gates,
        'family_accuracy':fam_acc,
        'baseline':{'best_transparent_baseline_macro_f1':best_baseline},
        'matched_context_control':{'full_context_accuracy':full_matched,'context_ablated_accuracy':ablation_acc},
        'nonclaims':['consciousness','phenomenal experience','personhood','general human-like understanding'],
    }


def main() -> None:
    ap=argparse.ArgumentParser()
    for name in ['cases','replay_cases','ablation_cases','live_predictions','replay_predictions','ablation_predictions','live_seal','replay_seal','ablation_seal','gold','baseline_report']:
        ap.add_argument('--'+name.replace('_','-'),dest=name,type=Path,required=True)
    ap.add_argument('--output',type=Path)
    args=ap.parse_args(); result=score(**{k:getattr(args,k).resolve() for k in vars(args) if k!='output'})
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output: args.output.write_text(text,encoding='utf-8')
    print(text,end='')

if __name__=='__main__': main()
