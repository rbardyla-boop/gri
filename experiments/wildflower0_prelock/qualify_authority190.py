from __future__ import annotations
import sys, json, numpy as np, torch
sys.path.insert(0,'/tmp/wfcommit')
from probe_innovation_model import InnovationModel, train, pre, evaluate as eval_ungated
from wildflower0.nursery1 import MODES, collect_pairs, select_balanced_episode_seeds, set_seed, stable_hash

MODEL_SEED=190
THRESHOLD=0.30
WIDTH=0.30
DECAY=0.998
TRAIN_PER_MODE=2
TEST_PER_MODE=2
EPISODE_LENGTH=420
TRAIN_STEPS=80
BURN=12

def eval_authority(model,pairs,h,event_only=False):
 c,t,a=pre(pairs); scale=5.5; em=[]; eb=[]; scores=[]; alphas=[]; model.eval()
 with torch.no_grad():
  for st in range(BURN+2,len(pairs)-h,max(h,4)):
   if event_only and not any(pairs[st+k].rule_event or pairs[st+k].collision or pairs[st+k].boundary for k in range(h)):
    continue
   hidden=torch.zeros((1,64)); hist=[]
   for i in range(st-BURN,st):
    s=torch.tensor(c[i][None]); p=torch.tensor(c[i-1][None]); v=s-p; pp=torch.tensor(c[i-2][None]); inv=s-(p+(p-pp)).clamp(-1,1)
    _,hidden,_,_=model.step(s,v,torch.tensor([a[i]]),inv,hidden)
    hist.append(float(inv.abs().mean()*scale))
   w=np.geomspace(.35,1.0,len(hist)); score=float(np.dot(w,hist)/w.sum()); alpha=float(np.clip((score-THRESHOLD)/WIDTH,0,1))
   scores.append(score); alphas.append(alpha)
   state=torch.tensor(c[st][None]); prev=torch.tensor(c[st-1][None]); vel=state-prev; pp=torch.tensor(c[st-2][None]); inv=state-(prev+(prev-pp)).clamp(-1,1)
   bs=state.clone(); bv=vel.clone(); local=alpha
   for k in range(h):
    mp,hidden,_,_=model.step(state,vel,torch.tensor([a[st+k]]),inv,hidden); bp=(bs+bv).clamp(-1,1)
    pred=(bp+local*(mp-bp)).clamp(-1,1)
    vel=pred-state; state=pred; inv=inv*.90; bv=bp-bs; bs=bp; local*=DECAY
   ex=torch.tensor(t[st+h-1][None]); em.append(float((state-ex).abs().mean()*scale)); eb.append(float((bs-ex).abs().mean()*scale))
 return {'model':float(np.mean(em)),'baseline':float(np.mean(eb)),'ratio':float(np.mean(em)/max(np.mean(eb),1e-8)),'innovation_mean':float(np.mean(scores)),'authority_mean':float(np.mean(alphas))}

def main():
 set_seed(MODEL_SEED)
 train_sel=select_balanced_episode_seeds(MODEL_SEED+9000,TRAIN_PER_MODE,start=300000)
 test_sel=select_balanced_episode_seeds(MODEL_SEED+19000,TEST_PER_MODE,start=350000)
 model=InnovationModel(); order=[train_sel[m][i] for i in range(TRAIN_PER_MODE) for m in MODES]
 for i,s in enumerate(order): train(model,collect_pairs(s,EPISODE_LENGTH),TRAIN_STEPS,MODEL_SEED+10000+i)
 rows=[]
 for mode in MODES:
  for seed in test_sel[mode]:
   pairs=collect_pairs(seed,520)
   row={'mode':mode,'episode_seed':seed}
   for h in (1,8,32): row[f'h{h}']=eval_authority(model,pairs,h)
   row['event_h8']=eval_authority(model,pairs,8,event_only=True)
   # ungated control from same trained bytes
   for h in (1,8,32):
    me,be,_=eval_ungated(model,pairs,h)
    row[f'ungated_h{h}_ratio']=float(me/max(be,1e-8))
   rows.append(row)
 h1=[r['h1']['ratio'] for r in rows];h8=[r['h8']['ratio'] for r in rows];h32=[r['h32']['ratio'] for r in rows];ev=[r['event_h8']['ratio'] for r in rows]
 ung={h:[r[f'ungated_h{h}_ratio'] for r in rows] for h in (1,8,32)}
 aggregate={
  'h1_ratio_mean':float(np.mean(h1)),'h1_ratio_max':float(np.max(h1)),
  'h8_ratio_mean':float(np.mean(h8)),'h8_ratio_max':float(np.max(h8)),
  'h32_ratio_mean':float(np.mean(h32)),'h32_ratio_max':float(np.max(h32)),
  'event_h8_ratio_mean':float(np.mean(ev)),'event_h8_ratio_max':float(np.max(ev)),
  'ungated_h1_mean':float(np.mean(ung[1])),'ungated_h1_max':float(np.max(ung[1])),
  'ungated_h8_mean':float(np.mean(ung[8])),'ungated_h8_max':float(np.max(ung[8])),
  'ungated_h32_mean':float(np.mean(ung[32])),'ungated_h32_max':float(np.max(ung[32])),
 }
 gates={
  'h1_noninferior_all':aggregate['h1_ratio_max']<=1.10,
  'h8_better_all':aggregate['h8_ratio_max']<=1.00,
  'h8_mean_10pct':aggregate['h8_ratio_mean']<=0.90,
  'h32_better_all':aggregate['h32_ratio_max']<=1.00,
  'h32_mean_15pct':aggregate['h32_ratio_mean']<=0.85,
  'event_h8_mean_10pct':aggregate['event_h8_ratio_mean']<=0.90,
 }
 report={'status':'WILDFLOWER_AUTHORITY_FRESH_QUALIFICATION','model_seed':MODEL_SEED,'frozen_config':{'threshold_cells':THRESHOLD,'width_cells':WIDTH,'authority_decay':DECAY,'train_per_mode':TRAIN_PER_MODE,'test_per_mode':TEST_PER_MODE,'episode_length':EPISODE_LENGTH,'train_steps_per_episode':TRAIN_STEPS,'burn':BURN},'train_selection':train_sel,'test_selection':test_sel,'rows':rows,'aggregate':aggregate,'gates':gates,'passed':all(gates.values()),'architecture_freeze_authorized':False,'primitive0_authorized':False}
 report['receipt_sha256']=stable_hash(report)
 print(json.dumps(report,indent=2,sort_keys=True))
 return 0 if report['passed'] else 2
if __name__=='__main__': raise SystemExit(main())
