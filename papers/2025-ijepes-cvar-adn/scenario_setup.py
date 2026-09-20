"""Scenario and network setup for Xia et al. (2025) method-level reproduction."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import qmc, norm, t as student_t
from scipy.spatial.distance import cdist

np.set_printoptions(precision=4, suppress=True)
SEED = 123
rng = np.random.default_rng(SEED)

# Standard IEEE 33-bus data (MW / MVAr; branch R/X in ohm)
loads = {
2:(0.100,0.060),3:(0.090,0.040),4:(0.120,0.080),5:(0.060,0.030),6:(0.060,0.020),
7:(0.200,0.100),8:(0.200,0.100),9:(0.060,0.020),10:(0.060,0.020),11:(0.045,0.030),
12:(0.060,0.035),13:(0.060,0.035),14:(0.120,0.080),15:(0.060,0.010),16:(0.060,0.020),
17:(0.060,0.020),18:(0.090,0.040),19:(0.090,0.040),20:(0.090,0.040),21:(0.090,0.040),
22:(0.090,0.040),23:(0.090,0.050),24:(0.420,0.200),25:(0.420,0.200),26:(0.060,0.025),
27:(0.060,0.025),28:(0.060,0.020),29:(0.120,0.070),30:(0.200,0.600),31:(0.150,0.070),
32:(0.210,0.100),33:(0.060,0.040)
}
branches = [
(1,2,0.0922,0.0470),(2,3,0.4930,0.2511),(3,4,0.3660,0.1864),(4,5,0.3811,0.1941),
(5,6,0.8190,0.7070),(6,7,0.1872,0.6188),(7,8,1.7114,1.2351),(8,9,1.0300,0.7400),
(9,10,1.0440,0.7400),(10,11,0.1966,0.0650),(11,12,0.3744,0.1238),(12,13,1.4680,1.1550),
(13,14,0.5416,0.7129),(14,15,0.5910,0.5260),(15,16,0.7463,0.5450),(16,17,1.2890,1.7210),
(17,18,0.7320,0.5740),(2,19,0.1640,0.1565),(19,20,1.5042,1.3554),(20,21,0.4095,0.4784),
(21,22,0.7089,0.9373),(3,23,0.4512,0.3083),(23,24,0.8980,0.7091),(24,25,0.8960,0.7011),
(6,26,0.2030,0.1034),(26,27,0.2842,0.1447),(27,28,1.0590,0.9337),(28,29,0.8042,0.7006),
(29,30,0.5075,0.2585),(30,31,0.9744,0.9630),(31,32,0.3105,0.3619),(32,33,0.3410,0.5302),
]

children={i:[] for i in range(1,34)}
parent={}
for a,b,r,x in branches:
    children[a].append(b)
    parent[b]=a

def descendants(i):
    out=[i]
    for c in children[i]:
        out.extend(descendants(c))
    return out

desc_sets={i:set(descendants(i)) for i in range(1,34)}
baseKV=12.66
baseMVA=10.0
zbase=baseKV**2/baseMVA
P0=np.zeros(34)
Q0=np.zeros(34)
for i,(p,q) in loads.items():
    P0[i]=p
    Q0[i]=q

print('Total P/Q load =', P0.sum(), 'MW /', Q0.sum(), 'MVAr')
print('Paper DG/ESS placements: WT@17,32; PV@21,24; ESS@15,32')

# Fig. 8-inspired 24 h profiles. The paper does not publish the raw series.
hours=np.arange(1,25)
load_scale=np.array([0.62,0.58,0.56,0.55,0.58,0.66,0.76,0.86,0.94,1.00,1.02,0.99,
                     0.91,0.86,0.84,0.88,0.94,1.02,1.08,1.05,0.96,0.88,0.78,0.69])
pv_cf=np.array([0,0,0,0,0,0.02,0.12,0.30,0.52,0.72,0.88,0.96,0.92,0.78,0.58,0.36,0.15,0.03,0,0,0,0,0,0])
wind_cf=np.array([0.62,0.58,0.55,0.52,0.50,0.48,0.52,0.58,0.64,0.68,0.72,0.70,
                  0.66,0.62,0.60,0.58,0.61,0.66,0.72,0.78,0.82,0.78,0.72,0.66])
price=np.array([400]*8+[800,800,1200,1200,800,800,800,1200,1200,1200,1200,1200,1200,1200,800,800],dtype=float)

fig,ax=plt.subplots(figsize=(10,4))
ax.plot(hours, load_scale, marker='o', label='Load factor')
ax.plot(hours, pv_cf, marker='o', label='PV factor')
ax.plot(hours, wind_cf, marker='o', label='WT factor')
ax.set_xlabel('Hour')
ax.set_ylabel('p.u. factor')
ax.grid(alpha=.25)
ax.legend()
plt.show()

# 1000 spatiotemporally correlated scenarios via LHS + Gaussian copula.
pv_caps=np.array([0.6,0.6])
wind_caps=np.array([0.9,0.9])
n_raw=1000
D=5*24
sampler=qmc.LatinHypercube(d=D, seed=SEED)
U=sampler.random(n_raw)
Z=norm.ppf(U)

rho_t=.65
Tcorr=rho_t**np.abs(np.subtract.outer(np.arange(24),np.arange(24)))
Vcorr=np.array([
[1.0,.75,.20,.15,.10],
[.75,1.0,.15,.20,.10],
[.20,.15,1.0,.65,.10],
[.15,.20,.65,1.0,.10],
[.10,.10,.10,.10,1.0],
])
C=np.kron(Tcorr,Vcorr)
L=np.linalg.cholesky(C+1e-8*np.eye(D))
Zc=Z@L.T
Uc=np.clip(norm.cdf(Zc),1e-6,1-1e-6).reshape(n_raw,24,5)

pv_sigma=0.08+0.08*pv_cf
wind_sigma=np.full(24,0.14)
load_sigma=0.04+0.01*(load_scale>0.95)
df=5
pv_scen=np.zeros((n_raw,24,2))
wind_scen=np.zeros((n_raw,24,2))
load_scen=np.zeros((n_raw,24))
for h in range(24):
    for k in range(2):
        e=student_t.ppf(Uc[:,h,k],df=df)*pv_sigma[h]*pv_caps[k]
        pv_scen[:,h,k]=np.clip(pv_cf[h]*pv_caps[k]+e,0,pv_caps[k])
    for k in range(2):
        e=student_t.ppf(Uc[:,h,2+k],df=df)*wind_sigma[h]*wind_caps[k]
        wind_scen[:,h,k]=np.clip(wind_cf[h]*wind_caps[k]+e,0,wind_caps[k])
    e=norm.ppf(Uc[:,h,4])*load_sigma[h]
    load_scen[:,h]=np.clip(load_scale[h]*(1+e),0.4,1.25)

print('raw scenarios:', pv_scen.shape[0])

X=np.concatenate([
    pv_scen.reshape(n_raw,-1)/0.6,
    wind_scen.reshape(n_raw,-1)/0.9,
    load_scen
],axis=1)

def fast_forward_reduce(X,k,probs=None):
    n=len(X)
    if probs is None:
        probs=np.full(n,1/n)
    D=cdist(X,X)
    selected=[]
    nearest=np.full(n,np.inf)
    candidates=set(range(n))
    for _ in range(k):
        best=None
        best_obj=np.inf
        best_nearest=None
        for j in candidates:
            candidate=np.minimum(nearest,D[:,j])
            obj=float(probs@candidate)
            if obj<best_obj:
                best_obj=obj
                best=j
                best_nearest=candidate
        selected.append(best)
        candidates.remove(best)
        nearest=best_nearest
    sel=np.array(selected)
    assignment=D[:,sel].argmin(axis=1)
    p_red=np.array([probs[assignment==j].sum() for j in range(k)])
    return sel,p_red,assignment

sel,p_red,assignment=fast_forward_reduce(X,20)
pvR=pv_scen[sel]
windR=wind_scen[sel]
loadR=load_scen[sel]
print('reduced scenarios:',len(sel),'probability sum:',p_red.sum(),'range:',(p_red.min(),p_red.max()))

net_load_plot=3.715*loadR-pvR.sum(axis=2)-windR.sum(axis=2)
fig,ax=plt.subplots(figsize=(10,4))
for s in range(20):
    ax.plot(hours,net_load_plot[s],alpha=.35)
ax.plot(hours,(p_red[:,None]*net_load_plot).sum(0),linewidth=2.5,label='Probability-weighted mean')
ax.set_xlabel('Hour')
ax.set_ylabel('System net load (MW)')
ax.grid(alpha=.25)
ax.legend()
plt.show()

# LinDistFlow approximation used instead of the paper's DistFlow + MISOCP.
def lindistflow_v2(Pnode,Qnode):
    v=np.ones(34)
    Pflow=np.zeros(len(branches))
    Qflow=np.zeros(len(branches))
    for ei,(a,b,r,x) in enumerate(branches):
        ds=desc_sets[b]
        P=Pnode[list(ds)].sum()
        Q=Qnode[list(ds)].sum()
        Pflow[ei]=P
        Qflow[ei]=Q
        v[b]=v[a]-2*((r/zbase)*(P/baseMVA)+(x/zbase)*(Q/baseMVA))
    return v,Pflow,Qflow

crit=[18,22,25,33]
ess_buses=[15,32]
sens=np.zeros((len(crit),2))
for k,bus in enumerate(ess_buses):
    p=np.zeros(34)
    q=np.zeros(34)
    p[bus]=1.0
    v,_,_=lindistflow_v2(p,q)
    sens[:,k]=v[crit]-1.0

S=20
T=24
base_v=np.zeros((S,T,len(crit)))
net_total=np.zeros((S,T))
for s in range(S):
    for h in range(T):
        P=P0*loadR[s,h]
        Q=Q0*loadR[s,h]
        P=P.copy()
        Q=Q.copy()
        P[21]-=pvR[s,h,0]
        P[24]-=pvR[s,h,1]
        P[17]-=windR[s,h,0]
        P[32]-=windR[s,h,1]
        v,_,_=lindistflow_v2(P,Q)
        base_v[s,h]=v[crit]
        net_total[s,h]=P.sum()

print('Without ESS, critical-bus voltage range:',np.sqrt(base_v).min(),np.sqrt(base_v).max())
print('Voltage sensitivity (squared-voltage change per +1 MW ESS charging load):')
print(pd.DataFrame(sens,index=[f'bus {b}' for b in crit],columns=['ESS@15','ESS@32']).to_string())
