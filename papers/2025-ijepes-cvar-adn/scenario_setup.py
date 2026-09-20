"""Scenario generation and pandapower AC-grid setup for Xia et al. (2025) reproduction."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pandapower as pp
import pandapower.networks as pn
from scipy.stats import qmc, norm, t as student_t
from scipy.spatial.distance import cdist

np.set_printoptions(precision=4, suppress=True)
SEED = 123
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------
# 1) IEEE 33-bus benchmark directly from pandapower
# ---------------------------------------------------------------------
net = pn.case33bw()

base_load_p = net.load["p_mw"].to_numpy(dtype=float).copy()
base_load_q = net.load["q_mvar"].to_numpy(dtype=float).copy()
print(
    "IEEE 33-bus base load:",
    f"{base_load_p.sum():.3f} MW / {base_load_q.sum():.3f} MVAr",
)

# Paper bus numbering starts at 1; pandapower case33bw bus indices start at 0.
def pp_bus(paper_bus):
    return int(paper_bus) - 1

pv_idx = np.array([
    pp.create_sgen(net, bus=pp_bus(21), p_mw=0.0, q_mvar=0.0, name="PV@21"),
    pp.create_sgen(net, bus=pp_bus(24), p_mw=0.0, q_mvar=0.0, name="PV@24"),
], dtype=int)

wt_idx = np.array([
    pp.create_sgen(net, bus=pp_bus(17), p_mw=0.0, q_mvar=0.0, name="WT@17"),
    pp.create_sgen(net, bus=pp_bus(32), p_mw=0.0, q_mvar=0.0, name="WT@32"),
], dtype=int)

ess_idx = np.array([
    pp.create_storage(
        net,
        bus=pp_bus(15),
        p_mw=0.0,
        q_mvar=0.0,
        max_e_mwh=1.8,
        min_e_mwh=0.18,
        soc_percent=50.0,
        name="ESS@15",
    ),
    pp.create_storage(
        net,
        bus=pp_bus(32),
        p_mw=0.0,
        q_mvar=0.0,
        max_e_mwh=1.0,
        min_e_mwh=0.10,
        soc_percent=50.0,
        name="ESS@32",
    ),
], dtype=int)

print("Paper placements: WT@17,32; PV@21,24; ESS@15,32")
print("pandapower indices:", {"PV": pv_idx.tolist(), "WT": wt_idx.tolist(), "ESS": ess_idx.tolist()})

# ---------------------------------------------------------------------
# 2) 24 h profiles and paper time-of-use tariff
# ---------------------------------------------------------------------
hours = np.arange(1, 25)

# The paper does not publish the numerical values behind Fig. 8.
# These deterministic curves reproduce the published trend only.
load_scale = np.array([
    0.62,0.58,0.56,0.55,0.58,0.66,0.76,0.86,0.94,1.00,1.02,0.99,
    0.91,0.86,0.84,0.88,0.94,1.02,1.08,1.05,0.96,0.88,0.78,0.69
])
pv_cf = np.array([
    0,0,0,0,0,0.02,0.12,0.30,0.52,0.72,0.88,0.96,
    0.92,0.78,0.58,0.36,0.15,0.03,0,0,0,0,0,0
])
wind_cf = np.array([
    0.62,0.58,0.55,0.52,0.50,0.48,0.52,0.58,0.64,0.68,0.72,0.70,
    0.66,0.62,0.60,0.58,0.61,0.66,0.72,0.78,0.82,0.78,0.72,0.66
])
price = np.array(
    [400]*8 + [800,800,1200,1200,800,800,800,1200,1200,1200,1200,1200,1200,1200,800,800],
    dtype=float,
)

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(hours, load_scale, marker="o", label="Load factor")
ax.plot(hours, pv_cf, marker="o", label="PV factor")
ax.plot(hours, wind_cf, marker="o", label="WT factor")
ax.set_xlabel("Hour")
ax.set_ylabel("p.u. factor")
ax.grid(alpha=.25)
ax.legend()
plt.show()

# ---------------------------------------------------------------------
# 3) 1000 correlated forecast-error scenarios
# ---------------------------------------------------------------------
pv_caps = np.array([0.6, 0.6])
wind_caps = np.array([0.9, 0.9])
n_raw = 1000
D = 5 * 24

sampler = qmc.LatinHypercube(d=D, seed=SEED)
U = sampler.random(n_raw)
Z = norm.ppf(U)

rho_t = 0.65
Tcorr = rho_t ** np.abs(np.subtract.outer(np.arange(24), np.arange(24)))
Vcorr = np.array([
    [1.0,.75,.20,.15,.10],
    [.75,1.0,.15,.20,.10],
    [.20,.15,1.0,.65,.10],
    [.15,.20,.65,1.0,.10],
    [.10,.10,.10,.10,1.0],
])

C = np.kron(Tcorr, Vcorr)
L = np.linalg.cholesky(C + 1e-8*np.eye(D))
Zc = Z @ L.T
Uc = np.clip(norm.cdf(Zc), 1e-6, 1-1e-6).reshape(n_raw, 24, 5)

pv_sigma = 0.08 + 0.08*pv_cf
wind_sigma = np.full(24, 0.14)
load_sigma = 0.04 + 0.01*(load_scale > 0.95)
df = 5

pv_scen = np.zeros((n_raw, 24, 2))
wind_scen = np.zeros((n_raw, 24, 2))
load_scen = np.zeros((n_raw, 24))

for h in range(24):
    for k in range(2):
        e = student_t.ppf(Uc[:, h, k], df=df) * pv_sigma[h] * pv_caps[k]
        pv_scen[:, h, k] = np.clip(pv_cf[h]*pv_caps[k] + e, 0, pv_caps[k])
    for k in range(2):
        e = student_t.ppf(Uc[:, h, 2+k], df=df) * wind_sigma[h] * wind_caps[k]
        wind_scen[:, h, k] = np.clip(wind_cf[h]*wind_caps[k] + e, 0, wind_caps[k])
    e = norm.ppf(Uc[:, h, 4]) * load_sigma[h]
    load_scen[:, h] = np.clip(load_scale[h]*(1+e), 0.4, 1.25)

print("raw scenarios:", pv_scen.shape[0])

# ---------------------------------------------------------------------
# 4) Fast-forward style representative-scenario selection: 1000 -> 20
# ---------------------------------------------------------------------
X = np.concatenate([
    pv_scen.reshape(n_raw, -1) / 0.6,
    wind_scen.reshape(n_raw, -1) / 0.9,
    load_scen,
], axis=1)

def fast_forward_reduce(X, k, probs=None):
    n = len(X)
    if probs is None:
        probs = np.full(n, 1/n)
    Dmat = cdist(X, X)
    selected = []
    nearest = np.full(n, np.inf)
    candidates = set(range(n))
    for _ in range(k):
        best = None
        best_obj = np.inf
        best_nearest = None
        for j in candidates:
            candidate = np.minimum(nearest, Dmat[:, j])
            obj = float(probs @ candidate)
            if obj < best_obj:
                best_obj = obj
                best = j
                best_nearest = candidate
        selected.append(best)
        candidates.remove(best)
        nearest = best_nearest

    sel = np.array(selected)
    assignment = Dmat[:, sel].argmin(axis=1)
    p_red = np.array([probs[assignment == j].sum() for j in range(k)])
    return sel, p_red, assignment

sel, p_red, assignment = fast_forward_reduce(X, 20)
pvR = pv_scen[sel]
windR = wind_scen[sel]
loadR = load_scen[sel]

print(
    "reduced scenarios:",
    len(sel),
    "probability sum:",
    p_red.sum(),
    "range:",
    (p_red.min(), p_red.max()),
)

net_load_plot = 3.715*loadR - pvR.sum(axis=2) - windR.sum(axis=2)
fig, ax = plt.subplots(figsize=(10, 4))
for s in range(20):
    ax.plot(hours, net_load_plot[s], alpha=.35)
ax.plot(
    hours,
    (p_red[:, None]*net_load_plot).sum(0),
    linewidth=2.5,
    label="Probability-weighted mean",
)
ax.set_xlabel("Hour")
ax.set_ylabel("System net load (MW)")
ax.grid(alpha=.25)
ax.legend()
plt.show()

# ---------------------------------------------------------------------
# 5) Full AC power flow in pandapower
# ---------------------------------------------------------------------
crit_paper_buses = np.array([18, 22, 25, 33], dtype=int)
crit_pp_buses = np.array([pp_bus(b) for b in crit_paper_buses], dtype=int)
ess_caps_mwh = np.array([1.8, 1.0])
ess_pmax_mw = np.array([0.3, 0.2])

def set_operating_point(s, h, storage_p_mw=(0.0, 0.0)):
    """Write one scenario/hour operating point into the pandapower network.

    pandapower storage convention: positive p_mw = charging (consumption),
    negative p_mw = discharging (generation).
    """
    net.load.loc[:, "p_mw"] = base_load_p * loadR[s, h]
    net.load.loc[:, "q_mvar"] = base_load_q * loadR[s, h]

    net.sgen.loc[pv_idx, "p_mw"] = pvR[s, h, :]
    net.sgen.loc[pv_idx, "q_mvar"] = 0.0
    net.sgen.loc[wt_idx, "p_mw"] = windR[s, h, :]
    net.sgen.loc[wt_idx, "q_mvar"] = 0.0

    net.storage.loc[ess_idx, "p_mw"] = np.asarray(storage_p_mw, dtype=float)
    net.storage.loc[ess_idx, "q_mvar"] = 0.0

def run_ac_case(s, h, storage_p_mw=(0.0, 0.0), init="auto"):
    set_operating_point(s, h, storage_p_mw)
    pp.runpp(
        net,
        algorithm="bfsw",
        calculate_voltage_angles=False,
        init=init,
        voltage_depend_loads=False,
        check_connectivity=True,
    )
    if not net.converged:
        raise RuntimeError(f"pandapower did not converge for scenario={s}, hour={h}")
    return {
        "vm_pu": net.res_bus["vm_pu"].to_numpy(dtype=float).copy(),
        "p_grid_mw": float(net.res_ext_grid["p_mw"].iloc[0]),
        "q_grid_mvar": float(net.res_ext_grid["q_mvar"].iloc[0]),
        "loss_mw": float(net.res_line["pl_mw"].sum()),
    }

# Baseline AC power flow and finite-difference sensitivities around p_storage=0.
S = 20
T = 24
B = len(crit_pp_buses)
K = 2
delta_mw = 0.02

base_vm = np.zeros((S, T, len(net.bus)))
base_grid_p = np.zeros((S, T))
base_losses = np.zeros((S, T))
dv_dp = np.zeros((S, T, B, K))
dgrid_dp = np.zeros((S, T, K))

for s in range(S):
    for h in range(T):
        base = run_ac_case(s, h, (0.0, 0.0), init="auto")
        base_vm[s, h] = base["vm_pu"]
        base_grid_p[s, h] = base["p_grid_mw"]
        base_losses[s, h] = base["loss_mw"]

        for k in range(K):
            p_plus = np.zeros(K)
            p_minus = np.zeros(K)
            p_plus[k] = delta_mw
            p_minus[k] = -delta_mw

            plus = run_ac_case(s, h, p_plus, init="auto")
            minus = run_ac_case(s, h, p_minus, init="auto")

            dv_dp[s, h, :, k] = (
                plus["vm_pu"][crit_pp_buses] - minus["vm_pu"][crit_pp_buses]
            ) / (2*delta_mw)

            dgrid_dp[s, h, k] = (
                plus["p_grid_mw"] - minus["p_grid_mw"]
            ) / (2*delta_mw)

print(
    "Baseline AC voltage range:",
    f"{base_vm.min():.4f} - {base_vm.max():.4f} p.u.",
)
print(
    "Mean active network loss:",
    f"{np.sum(p_red[:,None]*base_losses)/24:.4f} MW",
)
print("AC finite-difference dV/dP_storage at representative operating point:")
rep = pd.DataFrame(
    dv_dp[0, 12],
    index=[f"bus {b}" for b in crit_paper_buses],
    columns=["ESS@15", "ESS@32"],
)
print(rep.to_string())
