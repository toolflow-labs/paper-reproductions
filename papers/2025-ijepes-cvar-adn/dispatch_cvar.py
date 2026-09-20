"""CVaR ESS dispatch experiment for Xia et al. (2025) method-level reproduction."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import linprog
from scipy.sparse import csr_matrix
from scenario_setup import p_red, price, base_v, sens, crit, net_total, hours

def solve_dispatch(lambda_risk=0.0,beta=0.95,kv=50000.0,cycle_cost=30.0,export_frac=0.15,vmin=0.94,vmax=1.06):
    S,T,K,B=20,24,2,len(crit)
    idx={}
    n=0
    def alloc(name,shape):
        nonlocal n
        arr=np.arange(n,n+int(np.prod(shape))).reshape(shape)
        idx[name]=arr
        n+=arr.size
        return arr

    pch=alloc('pch',(K,T))
    pdis=alloc('pdis',(K,T))
    soc=alloc('soc',(K,T+1))
    gimp=alloc('gimp',(S,T))
    gexp=alloc('gexp',(S,T))
    vlo=alloc('vlo',(S,T,B))
    vhi=alloc('vhi',(S,T,B))
    eta_c=alloc('eta_c',(1,))
    zc=alloc('zc',(S,))
    eta_v=alloc('eta_v',(1,))
    zv=alloc('zv',(S,))

    c=np.zeros(n)
    for s in range(S):
        ps=p_red[s]
        for h in range(T):
            c[gimp[s,h]]+=(1-lambda_risk)*ps*price[h]
            c[gexp[s,h]]+=(1-lambda_risk)*ps*(-export_frac*price[h])
            for k in range(K):
                c[pch[k,h]]+=(1-lambda_risk)*ps*cycle_cost
                c[pdis[k,h]]+=(1-lambda_risk)*ps*cycle_cost
            for b in range(B):
                c[vlo[s,h,b]]+=(1-lambda_risk)*ps*kv/B
                c[vhi[s,h,b]]+=(1-lambda_risk)*ps*kv/B

    # CVaR linear objective terms.
    c[eta_c[0]]+=lambda_risk
    c[zc]+=lambda_risk*p_red/(1-beta)
    c[eta_v[0]]+=lambda_risk
    c[zv]+=lambda_risk*p_red/(1-beta)

    # Equalities: SOC dynamics + per-scenario power balance.
    rr=[]
    cc=[]
    dd=[]
    beq=[]
    r=0
    caps=np.array([1.8,1.0])
    pmax=np.array([0.3,0.2])
    eta_ch=.95
    eta_dis=.95
    init=.5

    for k in range(K):
        rr.append(r);cc.append(soc[k,0]);dd.append(1);beq.append(caps[k]*init);r+=1
        for h in range(T):
            for col,val in [
                (soc[k,h+1],1),
                (soc[k,h],-1),
                (pch[k,h],-eta_ch),
                (pdis[k,h],1/eta_dis)
            ]:
                rr.append(r);cc.append(col);dd.append(val)
            beq.append(0);r+=1
        rr.append(r);cc.append(soc[k,T]);dd.append(1);beq.append(caps[k]*init);r+=1

    for s in range(S):
        for h in range(T):
            for col,val in [(gimp[s,h],1),(gexp[s,h],-1)]:
                rr.append(r);cc.append(col);dd.append(val)
            for k in range(K):
                rr += [r,r]
                cc += [pdis[k,h],pch[k,h]]
                dd += [1,-1]
            beq.append(net_total[s,h])
            r+=1

    Aeq=csr_matrix((dd,(rr,cc)),shape=(r,n))
    beq=np.array(beq)

    # Inequalities: voltage slacks + CVaR linearization.
    rr=[]
    cc=[]
    dd=[]
    bub=[]
    r=0
    lo2=vmin**2
    hi2=vmax**2

    for s in range(S):
        for h in range(T):
            for bi in range(B):
                # vlo >= lo2 - v2
                rr.append(r);cc.append(vlo[s,h,bi]);dd.append(-1)
                for k in range(K):
                    rr += [r,r]
                    cc += [pch[k,h],pdis[k,h]]
                    dd += [-sens[bi,k],sens[bi,k]]
                bub.append(base_v[s,h,bi]-lo2)
                r+=1

                # vhi >= v2 - hi2
                rr.append(r);cc.append(vhi[s,h,bi]);dd.append(-1)
                for k in range(K):
                    rr += [r,r]
                    cc += [pch[k,h],pdis[k,h]]
                    dd += [sens[bi,k],-sens[bi,k]]
                bub.append(hi2-base_v[s,h,bi])
                r+=1

    # Economic CVaR: z_s >= cost_s - eta.
    for s in range(S):
        for h in range(T):
            rr += [r,r]
            cc += [gimp[s,h],gexp[s,h]]
            dd += [price[h],-export_frac*price[h]]
            for k in range(K):
                rr += [r,r]
                cc += [pch[k,h],pdis[k,h]]
                dd += [cycle_cost,cycle_cost]
        rr += [r,r]
        cc += [eta_c[0],zc[s]]
        dd += [-1,-1]
        bub.append(0)
        r+=1

    # Network-risk CVaR.
    for s in range(S):
        for h in range(T):
            for bi in range(B):
                rr += [r,r]
                cc += [vlo[s,h,bi],vhi[s,h,bi]]
                dd += [kv/B,kv/B]
        rr += [r,r]
        cc += [eta_v[0],zv[s]]
        dd += [-1,-1]
        bub.append(0)
        r+=1

    Aub=csr_matrix((dd,(rr,cc)),shape=(r,n))
    bub=np.array(bub)

    bounds=[(0,None)]*n
    for k in range(K):
        for h in range(T):
            bounds[pch[k,h]]=(0,pmax[k])
            bounds[pdis[k,h]]=(0,pmax[k])
        for h in range(T+1):
            bounds[soc[k,h]]=(0.1*caps[k],caps[k])

    for s in range(S):
        for h in range(T):
            bounds[gimp[s,h]]=(0,10)
            bounds[gexp[s,h]]=(0,10)

    bounds[eta_c[0]]=(0,None)
    bounds[eta_v[0]]=(0,None)

    result=linprog(c,A_ub=Aub,b_ub=bub,A_eq=Aeq,b_eq=beq,bounds=bounds,method='highs')
    if not result.success:
        raise RuntimeError(result.message)

    pars=dict(
        kv=kv,
        cycle_cost=cycle_cost,
        export_frac=export_frac,
        beta=beta,
        lambda_risk=lambda_risk,
        vmin=vmin,
        vmax=vmax
    )
    return result,idx,pars

def weighted_cvar(vals,probs,beta):
    vals=np.asarray(vals)
    candidates=np.unique(vals)
    objectives=[
        eta+np.sum(probs*np.maximum(vals-eta,0))/(1-beta)
        for eta in candidates
    ]
    j=int(np.argmin(objectives))
    return float(objectives[j]),float(candidates[j])

def evaluate(result,idx,pars):
    x=result.x
    pch=x[idx['pch']]
    pdis=x[idx['pdis']]
    soc=x[idx['soc']]
    gimp=x[idx['gimp']]
    gexp=x[idx['gexp']]

    v2=np.zeros((20,24,len(crit)))
    for s in range(20):
        for h in range(24):
            v2[s,h]=base_v[s,h]+sens@(pch[:,h]-pdis[:,h])

    v=np.sqrt(np.maximum(v2,0))
    lo=np.maximum(0,pars['vmin']-v)
    hi=np.maximum(0,v-pars['vmax'])
    lo2=np.maximum(0,pars['vmin']**2-v2)
    hi2=np.maximum(0,v2-pars['vmax']**2)

    cost=np.array([
        np.sum(price*gimp[s]-pars['export_frac']*price*gexp[s])
        +pars['cycle_cost']*np.sum(pch+pdis)
        for s in range(20)
    ])
    risk=pars['kv']/len(crit)*np.sum(lo2+hi2,axis=(1,2))

    cc,_=weighted_cvar(cost,p_red,pars['beta'])
    cr,_=weighted_cvar(risk,p_red,pars['beta'])

    return dict(
        pch=pch,
        pdis=pdis,
        soc=soc,
        gimp=gimp,
        gexp=gexp,
        v=v,
        cost_s=cost,
        risk_s=risk,
        expected_cost=float(p_red@cost),
        expected_risk=float(p_red@risk),
        cvar_cost=cc,
        cvar_risk=cr,
        violation_pu_h=float(np.sum(p_red[:,None,None]*(lo+hi))),
        violation_probability=float(np.sum(p_red[:,None,None]*((lo+hi)>1e-9))/(24*len(crit))),
        vmin=float(v.min()),
        vmax=float(v.max()),
        peak_import=float((p_red[:,None]*gimp).sum(0).max())
    )

def evaluate_no_ess(kv=50000,export_frac=.15,beta=.95,vmin=.94,vmax=1.06):
    gimp=np.maximum(net_total,0)
    gexp=np.maximum(-net_total,0)
    v=np.sqrt(np.maximum(base_v,0))
    lo=np.maximum(0,vmin-v)
    hi=np.maximum(0,v-vmax)
    lo2=np.maximum(0,vmin**2-base_v)
    hi2=np.maximum(0,base_v-vmax**2)

    cost=np.array([
        np.sum(price*gimp[s]-export_frac*price*gexp[s])
        for s in range(20)
    ])
    risk=kv/len(crit)*np.sum(lo2+hi2,axis=(1,2))
    cc,_=weighted_cvar(cost,p_red,beta)
    cr,_=weighted_cvar(risk,p_red,beta)

    return dict(
        expected_cost=float(p_red@cost),
        expected_risk=float(p_red@risk),
        cvar_cost=cc,
        cvar_risk=cr,
        violation_pu_h=float(np.sum(p_red[:,None,None]*(lo+hi))),
        violation_probability=float(np.sum(p_red[:,None,None]*((lo+hi)>1e-9))/(24*len(crit))),
        vmin=float(v.min()),
        vmax=float(v.max()),
        peak_import=float((p_red[:,None]*gimp).sum(0).max()),
        v=v,
        gimp=gimp
    )

case1=evaluate_no_ess()
r2,i2,p2=solve_dispatch(lambda_risk=0.0,beta=.95)
case2=evaluate(r2,i2,p2)
r3,i3,p3=solve_dispatch(lambda_risk=0.9,beta=.95)
case3=evaluate(r3,i3,p3)

summary=pd.DataFrame([
    ['Case 1: no ESS',case1['expected_cost'],case1['cvar_cost'],case1['cvar_risk'],case1['violation_pu_h'],case1['vmin'],case1['peak_import']],
    ['Case 2: expected-value ESS',case2['expected_cost'],case2['cvar_cost'],case2['cvar_risk'],case2['violation_pu_h'],case2['vmin'],case2['peak_import']],
    ['Case 3: CVaR ESS',case3['expected_cost'],case3['cvar_cost'],case3['cvar_risk'],case3['violation_pu_h'],case3['vmin'],case3['peak_import']],
],columns=[
    'case',
    'expected economic cost',
    'CVaR economic cost',
    'CVaR network risk',
    'voltage violation p.u.-h',
    'minimum voltage',
    'peak expected import MW'
])
print(summary.round(4).to_string(index=False))

# ESS sequence and SOC.
fig,ax=plt.subplots(figsize=(10,4))
for label,case in [('Case 2 expected',case2),('Case 3 CVaR',case3)]:
    net=(case['pdis']-case['pch']).sum(axis=0)
    ax.step(hours,net,where='mid',label=label)
ax.axhline(0,linewidth=1)
ax.set_xlabel('Hour')
ax.set_ylabel('ESS net discharge power (MW)')
ax.grid(alpha=.25)
ax.legend()
plt.show()

fig,ax=plt.subplots(figsize=(10,4))
for k,name in enumerate(['ESS@15','ESS@32']):
    ax.plot(np.arange(25),case2['soc'][k],marker='o',alpha=.7,label=f'{name} - Case2')
    ax.plot(np.arange(25),case3['soc'][k],marker='x',alpha=.9,label=f'{name} - Case3')
ax.set_xlabel('Hour boundary')
ax.set_ylabel('Stored energy (MWh)')
ax.grid(alpha=.25)
ax.legend(ncol=2)
plt.show()

# Worst-scenario voltage comparison.
worst2=case2['v'].min(axis=(0,2))
worst3=case3['v'].min(axis=(0,2))
fig,ax=plt.subplots(figsize=(10,4))
ax.plot(hours,worst2,marker='o',label='Case 2 worst-scenario min V')
ax.plot(hours,worst3,marker='o',label='Case 3 CVaR worst-scenario min V')
ax.axhline(.94,linestyle='--',label='0.94 p.u. reference')
ax.set_xlabel('Hour')
ax.set_ylabel('Minimum voltage (p.u.)')
ax.grid(alpha=.25)
ax.legend()
plt.show()

# Risk-cost sensitivity.
rows=[]
for lam in [0,.25,.5,.75,.9]:
    rr,ii,pp=solve_dispatch(lambda_risk=lam,beta=.95)
    ee=evaluate(rr,ii,pp)
    rows.append([
        lam,
        ee['expected_cost'],
        ee['cvar_risk'],
        ee['violation_pu_h'],
        ee['vmin']
    ])

sens_df=pd.DataFrame(rows,columns=[
    'risk weight λ',
    'expected cost',
    'CVaR network risk',
    'voltage violation p.u.-h',
    'minimum voltage'
])
print(sens_df.round(4).to_string(index=False))

fig,ax=plt.subplots(figsize=(6,4))
ax.plot(sens_df['expected cost'],sens_df['CVaR network risk'],marker='o')
for _,r in sens_df.iterrows():
    ax.annotate(
        f"λ={r['risk weight λ']}",
        (r['expected cost'],r['CVaR network risk'])
    )
ax.set_xlabel('Expected economic cost')
ax.set_ylabel('CVaR network risk')
ax.grid(alpha=.25)
plt.show()
