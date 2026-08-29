from __future__ import annotations
import sys, random
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
sys.path.insert(0,'/tmp/wfcommit')
from wildflower0.nursery1 import MODES, collect_pairs, extract_object_state, select_balanced_episode_seeds, set_seed

class InnovationModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.emb=nn.Embedding(5,8)
        self.ctx=nn.GRUCell(26,64)
        self.corr=nn.Sequential(nn.Linear(90,96),nn.SiLU(),nn.Linear(96,6))
        self.auth=nn.Sequential(nn.Linear(90,48),nn.SiLU(),nn.Linear(48,1))
        nn.init.zeros_(self.corr[-1].weight); nn.init.zeros_(self.corr[-1].bias)
        nn.init.zeros_(self.auth[-1].weight); nn.init.constant_(self.auth[-1].bias,-2.5)
    def step(self,state,vel,action,innovation,hidden):
        e=self.emb(action.long()); inp=torch.cat((state,vel,e,innovation),1)
        hidden=self.ctx(inp,hidden); f=torch.cat((hidden,state,vel,e,innovation),1)
        correction=.30*torch.tanh(self.corr(f))
        authority=torch.sigmoid(self.auth(f))
        base=(state+vel).clamp(-1,1)
        pred=(base+authority*correction).clamp(-1,1)
        return pred,hidden,authority,correction

def pre(pairs):
 c=np.stack([extract_object_state(p.current.frame) for p in pairs]); t=np.stack([extract_object_state(p.nxt.frame) for p in pairs]); a=np.array([p.current.action for p in pairs]); return c,t,a

def prior_innov(c,index):
 # innovation known at state[index] from transition index-1 -> index
 prev=torch.tensor(c[index-1]); prevprev=torch.tensor(c[index-2])
 base=(prev+(prev-prevprev)).clamp(-1,1)
 return torch.tensor(c[index])-base

def train(model,pairs,steps,seed,horizon=8,burn=12,batch=24):
 c,t,a=pre(pairs); rng=np.random.default_rng(seed); opt=torch.optim.AdamW(model.parameters(),lr=1.4e-3,weight_decay=1e-4)
 starts_space=np.arange(burn+2,len(pairs)-horizon)
 model.train()
 for _ in range(steps):
  starts=rng.choice(starts_space,size=batch,replace=False); hidden=torch.zeros((batch,64))
  # observed history updates context. innovation is known from previous observed transition.
  for off in range(-burn,0):
   idx=starts+off; s=torch.tensor(c[idx]); p=torch.tensor(c[idx-1]); v=s-p
   pp=torch.tensor(c[idx-2]); inv=s-(p+(p-pp)).clamp(-1,1)
   _,hidden,_,_=model.step(s,v,torch.tensor(a[idx]),inv,hidden)
  state=torch.tensor(c[starts]); prev=torch.tensor(c[starts-1]); vel=state-prev
  prevprev=torch.tensor(c[starts-2]); inv=state-(prev+(prev-prevprev)).clamp(-1,1)
  loss=torch.zeros(())
  for k in range(horizon):
   action=torch.tensor(a[starts+k]); pred,hidden,auth,corr=model.step(state,vel,action,inv,hidden)
   base=(state+vel).clamp(-1,1); expected=torch.tensor(t[starts+k])
   me=(pred-expected).abs().mean(1); be=(base-expected).abs().mean(1)
   # Strongly discourage harm, but allow corrections where they earn it.
   loss += (1+.10*k)*(F.smooth_l1_loss(pred,expected)+2.5*F.relu(me-be).mean())
   loss += .010*auth.mean()+.005*corr.abs().mean()
   # auxiliary teacher-corrected one-step context teaches innovations explicitly
   if k < horizon-1:
     observed=expected
     observed_vel=observed-state
     observed_inv=observed-base
     # train an online-corrected one-step as additional signal
     tf_pred,_,tf_auth,tf_corr=model.step(observed,observed_vel,torch.tensor(a[starts+k+1]),observed_inv,hidden)
     tf_expected=torch.tensor(t[starts+k+1]); tf_base=(observed+observed_vel).clamp(-1,1)
     tf_me=(tf_pred-tf_expected).abs().mean(1); tf_be=(tf_base-tf_expected).abs().mean(1)
     loss += .30*(F.smooth_l1_loss(tf_pred,tf_expected)+2.0*F.relu(tf_me-tf_be).mean())
   vel=pred-state; state=pred; inv=inv*.90
  loss=loss/horizon
  if not torch.isfinite(loss): raise RuntimeError('nonfinite')
  opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1); opt.step()

def evaluate(model,pairs,h,burn=12,event_only=False):
 c,t,a=pre(pairs); scale=5.5; em=[]; eb=[]; auths=[]; model.eval()
 with torch.no_grad():
  for st in range(burn+2,len(pairs)-h,max(h,4)):
   if event_only and not any(pairs[st+k].rule_event or pairs[st+k].collision or pairs[st+k].boundary for k in range(h)): continue
   hidden=torch.zeros((1,64))
   for i in range(st-burn,st):
    s=torch.tensor(c[i][None]); p=torch.tensor(c[i-1][None]); v=s-p; pp=torch.tensor(c[i-2][None]); inv=s-(p+(p-pp)).clamp(-1,1)
    _,hidden,_,_=model.step(s,v,torch.tensor([a[i]]),inv,hidden)
   state=torch.tensor(c[st][None]); prev=torch.tensor(c[st-1][None]); vel=state-prev; pp=torch.tensor(c[st-2][None]); inv=state-(prev+(prev-pp)).clamp(-1,1)
   bs=state.clone(); bv=vel.clone(); aa=[]
   for k in range(h):
    pred,hidden,auth,_=model.step(state,vel,torch.tensor([a[st+k]]),inv,hidden); aa.append(float(auth.mean()))
    bp=(bs+bv).clamp(-1,1)
    vel=pred-state; state=pred; inv=inv*.90; bv=bp-bs; bs=bp
   ex=torch.tensor(t[st+h-1][None]); em.append(float((state-ex).abs().mean()*scale)); eb.append(float((bs-ex).abs().mean()*scale)); auths.append(np.mean(aa))
 return np.mean(em),np.mean(eb),np.mean(auths)

def run(seed=180):
 set_seed(seed); tr=select_balanced_episode_seeds(seed+9000,2,start=200000); te=select_balanced_episode_seeds(seed+19000,2,start=250000)
 m=InnovationModel(); order=[tr[x][i] for i in range(2) for x in MODES]
 for i,s in enumerate(order): train(m,collect_pairs(s,420),80,seed+10000+i)
 print('train',tr,'test',te)
 rows=[]
 for mode in MODES:
  for s in te[mode]:
   p=collect_pairs(s,520); r={'mode':mode,'seed':s}
   for h in (1,8,32):
    me,be,au=evaluate(m,p,h); r[f'h{h}']=me/max(be,1e-8); r[f'a{h}']=au
   me,be,au=evaluate(m,p,8,event_only=True); r['ev8']=me/max(be,1e-8)
   rows.append(r); print(r)
 print('agg', {k:(float(np.mean([r[k] for r in rows])),float(np.max([r[k] for r in rows]))) for k in ('h1','h8','h32','ev8')})
 return rows

if __name__=='__main__': run(int(sys.argv[1]) if len(sys.argv)>1 else 180)
