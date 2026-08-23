"""LCB failure-map simulations.

Purpose: attack, not rescue, the recovered flux-maintained-memory thesis.
Requires numpy and numba. All RNG seeds and sampled grids are fixed below.

The script evaluates:
1) recovered zero-detuning DPO/parametron normal form;
2) powered static bistable latch counterexample;
3) frame-equivalence fact for the parametron control;
4) nonreversible Langevin memory with unchanged stationary density.

No output from this script establishes a new primitive or thermodynamic advantage.
"""
from __future__ import annotations
import csv, json, math
from pathlib import Path
import numpy as np
from numba import njit

SEED=20260823

@njit(cache=True)
def dpo_dir(write_sign,sigma,trials,dt,t_write,t_hold,gamma,pump,g,write_force,bias,seed,withdraw_at,withdraw_hold):
    np.random.seed(seed); x=np.zeros(trials); y=np.zeros(trials)
    total=t_write+t_hold+(withdraw_hold if withdraw_at>=0 else 0.0)
    sq=math.sqrt(dt)
    for step in range(int(round(total/dt))):
        t=step*dt; h=write_sign*write_force if t<t_write else 0.0
        p=0.0 if withdraw_at>=0 and t>=withdraw_at else pump
        for j in range(trials):
            r2=x[j]*x[j]+y[j]*y[j]
            x[j]+=((-gamma+p)*x[j]-g*r2*x[j]+h+bias)*dt+sigma*sq*np.random.randn()
            y[j]+=((-gamma-p)*y[j]-g*r2*y[j])*dt+sigma*sq*np.random.randn()
    return x,y

def dpo_acc(**kw):
    p=dict(sigma=.05,trials=700,dt=.02,t_write=5.,t_hold=80.,gamma=1.,pump=1.4,g=1.,write_force=.4,bias=0.,withdraw_at=-1.,withdraw_hold=0.)
    p.update(kw); vals=[]
    for sign in (-1,1):
        x,_=dpo_dir(sign,p['sigma'],p['trials'],p['dt'],p['t_write'],p['t_hold'],p['gamma'],p['pump'],p['g'],p['write_force'],p['bias'],SEED+(sign+1)*137,p['withdraw_at'],p['withdraw_hold'])
        vals.append(float(np.mean(np.sign(x)==sign)))
    return sum(vals)/2

@njit(cache=True)
def latch_dir(write_sign,sigma,trials,dt,t_write,t_hold,mu_on,gamma_off,g,write_force,seed,withdraw_at,withdraw_hold):
    np.random.seed(seed); x=np.zeros(trials); sq=math.sqrt(dt)
    total=t_write+t_hold+(withdraw_hold if withdraw_at>=0 else 0.0)
    for step in range(int(round(total/dt))):
        t=step*dt; h=write_sign*write_force if t<t_write else 0.0
        powered=not(withdraw_at>=0 and t>=withdraw_at)
        for j in range(trials):
            drift=(mu_on*x[j]-g*x[j]**3+h) if powered else (-gamma_off*x[j]-g*x[j]**3)
            x[j]+=drift*dt+sigma*sq*np.random.randn()
    return x

def latch_acc(sigma=.05,hold=80,trials=700,mu=.4,force=.4,dur=5,dt=.02):
    vals=[]
    for sign in (-1,1):
        x=latch_dir(sign,sigma,trials,dt,dur,hold,mu,1.,1.,force,SEED+(sign+1)*137,-1.,0.)
        vals.append(float(np.mean(np.sign(x)==sign)))
    return sum(vals)/2

# Same-landscape nonequilibrium control.
# U=(x^2-1)^2/4+y^2/2.  Adding eps*J*grad(U) preserves exp(-U/D)
# but creates a nonzero stationary current for eps != 0.
@njit(cache=True)
def noneq_retention(eps,D,trials=1400,dt=.01,T=60.,seed=1):
    np.random.seed(seed); x=np.ones(trials); y=np.zeros(trials); flipped=np.zeros(trials,np.uint8)
    sq=math.sqrt(2*D*dt); grad2=0.; n=0; steps=int(T/dt)
    for s in range(steps):
        for i in range(trials):
            gx=x[i]*(x[i]*x[i]-1.); gy=y[i]
            x[i]+=(-gx-eps*gy)*dt+sq*np.random.randn()
            y[i]+=(-gy+eps*gx)*dt+sq*np.random.randn()
            if x[i]<0: flipped[i]=1
            if s>steps//2:
                gx2=x[i]*(x[i]*x[i]-1.); gy2=y[i]
                grad2+=gx2*gx2+gy2*gy2; n+=1
    return np.mean(x>0),np.mean(flipped==0),grad2/n

@njit(cache=True)
def noneq_autocorr(eps,D,trials=900,dt=.01,burn=35.,lag=10.,seed=1):
    np.random.seed(seed); x=np.empty(trials); y=np.zeros(trials); sq=math.sqrt(2*D*dt)
    for i in range(trials): x[i]=1. if i%2==0 else -1.
    for _ in range(int(burn/dt)):
        for i in range(trials):
            gx=x[i]*(x[i]*x[i]-1.); gy=y[i]
            x[i]+=(-gx-eps*gy)*dt+sq*np.random.randn(); y[i]+=(-gy+eps*gx)*dt+sq*np.random.randn()
    s0=np.where(x>=0,1.,-1.)
    for _ in range(int(lag/dt)):
        for i in range(trials):
            gx=x[i]*(x[i]*x[i]-1.); gy=y[i]
            x[i]+=(-gx-eps*gy)*dt+sq*np.random.randn(); y[i]+=(-gy+eps*gx)*dt+sq*np.random.randn()
    return np.mean(s0*np.where(x>=0,1.,-1.))

@njit(cache=True)
def noneq_final_sign(eps,x,y,dt=.002,T=30.):
    for _ in range(int(T/dt)):
        gx=x*(x*x-1.); gy=y
        x+=(-gx-eps*gy)*dt; y+=(-gy+eps*gx)*dt
    return 1 if x>=0 else -1

@njit(cache=True)
def basin_return(eps,R,n=2500,seed=1):
    np.random.seed(seed); good=0
    for _ in range(n):
        rad=R*math.sqrt(np.random.rand()); ang=2*math.pi*np.random.rand()
        if noneq_final_sign(eps,1+rad*math.cos(ang),rad*math.sin(ang))==1: good+=1
    return good/n

def run(outdir:Path):
    outdir.mkdir(parents=True,exist_ok=True)
    # compile
    dpo_dir(1,.01,5,.05,.1,.1,1,1.4,1,.4,0,1,-1,0); latch_dir(1,.01,5,.05,.1,.1,.4,1,1,.4,1,-1,0); noneq_retention(0,.1,5,.02,.1,1); noneq_autocorr(0,.1,10,.02,.1,.1,1); basin_return(0,.1,5,1)

    noise=[]
    for s in [0,.02,.05,.08,.10,.12,.15,.18,.20,.25,.30]:
        noise.append({'sigma':s,'dpo_accuracy':dpo_acc(sigma=s),'latch_accuracy':latch_acc(sigma=s)})

    hold=[]
    for s in [.08,.10,.12,.15,.18]:
        for t in [5,10,20,40,80,120,160,240]: hold.append({'sigma':s,'hold':t,'accuracy':dpo_acc(sigma=s,trials=350,dt=.025,t_hold=t)})

    mu=.4; barrier=mu*mu/4; pref=mu/(math.sqrt(2)*math.pi)
    krows=[]
    for s in [.10,.12,.15,.18]:
        vals=[]
        for r in hold:
            if r['sigma']==s and r['hold']>=20 and .5001<r['accuracy']<.9999:
                vals.append(-math.log(2*r['accuracy']-1)/(2*r['hold']))
        k=float(np.median(np.asarray(vals))); D=s*s/2; pred=pref*math.exp(-barrier/D)
        krows.append({'sigma':s,'barrier_over_D':barrier/D,'k_empirical':k,'k_kramers':pred,'ratio':k/pred})

    bias=[]; bcrit=2*mu**1.5/(3*math.sqrt(3.))
    for b in [-.14,-.12,-.10,-.08,-.06,-.04,-.02,0,.02,.04,.06,.08,.10,.12,.14]:
        dirs=[]
        for sign in (-1,1):
            x,_=dpo_dir(sign,.04,450,.02,5,80,1,1.4,1,.4,b,SEED+(sign+1)*199,-1,0); dirs.append(float(np.mean(np.sign(x)==sign)))
        bias.append({'bias':b,'acc_minus':dirs[0],'acc_plus':dirs[1]})

    withdraw=[]
    for after in [0,.25,.5,1,2,3,5,8,12,20]:
        x,y=dpo_dir(1,.02,600,.01,5,20,1,1.4,1,.4,0,SEED,25,after); amp=np.sqrt(x*x+y*y)
        xl=latch_dir(1,.02,600,.01,5,20,.4,1,1,.4,SEED,25,after)
        withdraw.append({'duration':after,'dpo_mean_amp':float(np.mean(amp)),'dpo_frac_gt_.2':float(np.mean(amp>.2)),'latch_mean_abs':float(np.mean(np.abs(xl))),'latch_frac_gt_.2':float(np.mean(np.abs(xl)>.2))})

    noneq=[]
    for D in [.05,.08,.10,.12]:
        for eps in [0,.25,.5,1,2,3,4]:
            end,surv,g2=noneq_retention(eps,D,seed=SEED+int(D*1000)+int(eps*10)); ac=noneq_autocorr(eps,D,seed=1234+int(D*1000)+int(eps*10))
            noneq.append({'D':D,'epsilon':eps,'end_correct':float(end),'no_flip_survival':float(surv),'sign_autocorr_lag10':float(ac),'estimated_epr':float((eps*eps/D)*g2 if eps else 0.)})
    basin=[]
    for R in [.25,.5,.75,1.,1.25,1.5]:
        for eps in [0,.25,.5,1,2,3,4]: basin.append({'radius':R,'epsilon':eps,'return_to_original':float(basin_return(eps,R,seed=SEED+int(R*100)+int(eps*10)))})

    frame={'rotating_states':[math.sqrt(mu),-math.sqrt(mu)],'rotating_state_derivative':0.0,'lab_description':'same states appear as carrier oscillations separated by pi phase','finding':'motion-versus-stasis is frame dependent for the parametron control'}
    result={'schema_version':1,'purpose':'failure discovery only','seed':SEED,'canonical':{'gamma':1.,'pump':1.4,'g':1.,'mu':mu,'barrier':barrier,'bias_saddle_node_abs':bcrit},'noise_comparison':noise,'hold_sweep':hold,'kramers_comparison':krows,'bias_sweep':bias,'withdrawal_comparison':withdraw,'frame_equivalence':frame,'same_landscape_nonequilibrium':noneq,'noneq_basin_recovery':basin,'nonclaims':['new primitive','thermodynamic advantage','hardware validation']}
    (outdir/'LCB_FAILURE_MAP_RESULTS.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'output':str(outdir/'LCB_FAILURE_MAP_RESULTS.json'),'kramers':krows},indent=2))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--outdir',type=Path,default=Path('artifacts/lcb_failure_map_v0')); args=ap.parse_args(); run(args.outdir)
