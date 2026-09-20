"""CVaR ESS dispatch using pandapower-calibrated AC sensitivities + full AC validation."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from scenario_setup import (
    p_red,
    price,
    hours,
    S,
    T,
    K,
    B,
    crit_paper_buses,
    ess_caps_mwh,
    ess_pmax_mw,
    base_grid_p,
    base_vm,
    dv_dp,
    dgrid_dp,
    run_ac_case,
)

def weighted_cvar(vals, probs, beta):
    """Discrete CVaR via Rockafellar-Uryasev representation."""
    vals = np.asarray(vals, dtype=float)
    candidates = np.unique(vals)
    objectives = [
        eta + np.sum(probs*np.maximum(vals - eta, 0.0))/(1-beta)
        for eta in candidates
    ]
    j = int(np.argmin(objectives))
    return float(objectives[j]), float(candidates[j])

def solve_dispatch(
    lambda_risk=0.0,
    beta=0.95,
    kv=50000.0,
    cycle_cost=30.0,
    export_frac=0.15,
    vmin=0.94,
    vmax=1.06,
):
    """Solve the 24 h, 2-ESS stochastic schedule as one linear program.

    Grid physics inside the LP is a local linearization whose base point and
    dV/dP, dPgrid/dP coefficients come from full pandapower AC power flows at
    every scenario-hour. The selected schedules are then validated by full
    nonlinear AC power flow again.
    """
    idx = {}
    n = 0

    def alloc(name, shape):
        nonlocal n
        arr = np.arange(n, n + int(np.prod(shape))).reshape(shape)
        idx[name] = arr
        n += arr.size
        return arr

    # p_storage = pch - pdis; positive = charging, matching pandapower.
    pch = alloc("pch", (K, T))
    pdis = alloc("pdis", (K, T))
    soc = alloc("soc", (K, T+1))
    gimp = alloc("gimp", (S, T))
    gexp = alloc("gexp", (S, T))
    vlo = alloc("vlo", (S, T, B))
    vhi = alloc("vhi", (S, T, B))
    eta_c = alloc("eta_c", (1,))
    zc = alloc("zc", (S,))
    eta_v = alloc("eta_v", (1,))
    zv = alloc("zv", (S,))

    c = np.zeros(n)

    # Expected-value part.
    for s in range(S):
        ps = p_red[s]
        for h in range(T):
            c[gimp[s, h]] += (1-lambda_risk) * ps * price[h]
            c[gexp[s, h]] += (1-lambda_risk) * ps * (-export_frac*price[h])

            # Throughput cost discourages simultaneous charge/discharge.
            for k in range(K):
                c[pch[k, h]] += (1-lambda_risk) * ps * cycle_cost
                c[pdis[k, h]] += (1-lambda_risk) * ps * cycle_cost

            for b in range(B):
                c[vlo[s, h, b]] += (1-lambda_risk) * ps * kv/B
                c[vhi[s, h, b]] += (1-lambda_risk) * ps * kv/B

    # CVaR terms.
    c[eta_c[0]] += lambda_risk
    c[zc] += lambda_risk * p_red/(1-beta)
    c[eta_v[0]] += lambda_risk
    c[zv] += lambda_risk * p_red/(1-beta)

    # Equalities: SOC dynamics + AC-linearized grid import.
    rr, cc, dd, beq = [], [], [], []
    r = 0
    eta_ch = 0.95
    eta_dis = 0.95
    init_soc = 0.50

    for k in range(K):
        rr.append(r); cc.append(soc[k, 0]); dd.append(1.0)
        beq.append(ess_caps_mwh[k]*init_soc)
        r += 1

        for h in range(T):
            for col, val in [
                (soc[k, h+1], 1.0),
                (soc[k, h], -1.0),
                (pch[k, h], -eta_ch),
                (pdis[k, h], 1.0/eta_dis),
            ]:
                rr.append(r); cc.append(col); dd.append(val)
            beq.append(0.0)
            r += 1

        rr.append(r); cc.append(soc[k, T]); dd.append(1.0)
        beq.append(ess_caps_mwh[k]*init_soc)
        r += 1

    # P_grid ≈ base_grid_p + sum dPgrid/dPstorage * (pch - pdis)
    # and P_grid = gimp - gexp.
    for s in range(S):
        for h in range(T):
            rr += [r, r]
            cc += [gimp[s, h], gexp[s, h]]
            dd += [1.0, -1.0]

            for k in range(K):
                gs = dgrid_dp[s, h, k]
                rr += [r, r]
                cc += [pch[k, h], pdis[k, h]]
                dd += [-gs, gs]

            beq.append(base_grid_p[s, h])
            r += 1

    Aeq = csr_matrix((dd, (rr, cc)), shape=(r, n))
    beq = np.asarray(beq)

    # Inequalities: AC-linearized voltage limits + CVaR linearization.
    rr, cc, dd, bub = [], [], [], []
    r = 0

    for s in range(S):
        for h in range(T):
            for bi, bus in enumerate(crit_paper_buses):
                base_v = base_vm[s, h, bus-1]

                # vlo >= vmin - V
                rr.append(r); cc.append(vlo[s, h, bi]); dd.append(-1.0)
                for k in range(K):
                    sv = dv_dp[s, h, bi, k]
                    rr += [r, r]
                    cc += [pch[k, h], pdis[k, h]]
                    dd += [-sv, sv]
                bub.append(base_v - vmin)
                r += 1

                # vhi >= V - vmax
                rr.append(r); cc.append(vhi[s, h, bi]); dd.append(-1.0)
                for k in range(K):
                    sv = dv_dp[s, h, bi, k]
                    rr += [r, r]
                    cc += [pch[k, h], pdis[k, h]]
                    dd += [sv, -sv]
                bub.append(vmax - base_v)
                r += 1

    # Economic CVaR: z_s >= cost_s - eta_c.
    for s in range(S):
        for h in range(T):
            rr += [r, r]
            cc += [gimp[s, h], gexp[s, h]]
            dd += [price[h], -export_frac*price[h]]

            for k in range(K):
                rr += [r, r]
                cc += [pch[k, h], pdis[k, h]]
                dd += [cycle_cost, cycle_cost]

        rr += [r, r]
        cc += [eta_c[0], zc[s]]
        dd += [-1.0, -1.0]
        bub.append(0.0)
        r += 1

    # Network-risk CVaR from voltage-limit slack.
    for s in range(S):
        for h in range(T):
            for bi in range(B):
                rr += [r, r]
                cc += [vlo[s, h, bi], vhi[s, h, bi]]
                dd += [kv/B, kv/B]

        rr += [r, r]
        cc += [eta_v[0], zv[s]]
        dd += [-1.0, -1.0]
        bub.append(0.0)
        r += 1

    Aub = csr_matrix((dd, (rr, cc)), shape=(r, n))
    bub = np.asarray(bub)

    bounds = [(0.0, None)] * n

    for k in range(K):
        for h in range(T):
            bounds[pch[k, h]] = (0.0, ess_pmax_mw[k])
            bounds[pdis[k, h]] = (0.0, ess_pmax_mw[k])
        for h in range(T+1):
            bounds[soc[k, h]] = (0.1*ess_caps_mwh[k], ess_caps_mwh[k])

    for s in range(S):
        for h in range(T):
            bounds[gimp[s, h]] = (0.0, 10.0)
            bounds[gexp[s, h]] = (0.0, 10.0)

    bounds[eta_c[0]] = (0.0, None)
    bounds[eta_v[0]] = (0.0, None)

    result = linprog(
        c,
        A_ub=Aub,
        b_ub=bub,
        A_eq=Aeq,
        b_eq=beq,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)

    pars = dict(
        kv=kv,
        cycle_cost=cycle_cost,
        export_frac=export_frac,
        beta=beta,
        lambda_risk=lambda_risk,
        vmin=vmin,
        vmax=vmax,
    )
    return result, idx, pars

def extract_schedule(result, idx):
    x = result.x
    return {
        "pch": x[idx["pch"]],
        "pdis": x[idx["pdis"]],
        "soc": x[idx["soc"]],
        "p_storage": x[idx["pch"]] - x[idx["pdis"]],
    }

def validate_schedule_ac(schedule, pars):
    """Score a selected schedule with full nonlinear pandapower AC power flow."""
    pch = schedule["pch"]
    pdis = schedule["pdis"]
    p_storage = schedule["p_storage"]

    vm = np.zeros((S, T, base_vm.shape[2]))
    p_grid = np.zeros((S, T))
    losses = np.zeros((S, T))

    for s in range(S):
        for h in range(T):
            out = run_ac_case(
                s,
                h,
                storage_p_mw=p_storage[:, h],
                init="auto",
            )
            vm[s, h] = out["vm_pu"]
            p_grid[s, h] = out["p_grid_mw"]
            losses[s, h] = out["loss_mw"]

    gimp = np.maximum(p_grid, 0.0)
    gexp = np.maximum(-p_grid, 0.0)

    crit_idx = crit_paper_buses - 1
    vcrit = vm[:, :, crit_idx]
    lo = np.maximum(0.0, pars["vmin"] - vcrit)
    hi = np.maximum(0.0, vcrit - pars["vmax"])

    throughput_cost = pars["cycle_cost"] * np.sum(pch + pdis)
    cost_s = np.array([
        np.sum(price*gimp[s] - pars["export_frac"]*price*gexp[s])
        + throughput_cost
        for s in range(S)
    ])

    risk_s = pars["kv"]/B * np.sum(lo + hi, axis=(1, 2))
    cvar_cost, var_cost = weighted_cvar(cost_s, p_red, pars["beta"])
    cvar_risk, var_risk = weighted_cvar(risk_s, p_red, pars["beta"])

    return {
        "pch": pch,
        "pdis": pdis,
        "soc": schedule["soc"],
        "p_storage": p_storage,
        "vm": vm,
        "p_grid": p_grid,
        "losses": losses,
        "cost_s": cost_s,
        "risk_s": risk_s,
        "expected_cost": float(p_red @ cost_s),
        "expected_risk": float(p_red @ risk_s),
        "cvar_cost": cvar_cost,
        "var_cost": var_cost,
        "cvar_risk": cvar_risk,
        "var_risk": var_risk,
        "violation_pu_h": float(np.sum(p_red[:, None, None]*(lo+hi))),
        "violation_probability": float(
            np.sum(p_red[:, None, None]*((lo+hi) > 1e-9))/(T*B)
        ),
        "vmin": float(vcrit.min()),
        "vmax": float(vcrit.max()),
        "peak_expected_import_mw": float((p_red[:, None]*gimp).sum(0).max()),
        "expected_loss_mwh": float(np.sum(p_red[:, None]*losses)),
    }

def validate_no_ess_ac(
    beta=0.95,
    kv=50000.0,
    cycle_cost=30.0,
    export_frac=0.15,
    vmin=0.94,
    vmax=1.06,
):
    pars = dict(
        beta=beta,
        kv=kv,
        cycle_cost=cycle_cost,
        export_frac=export_frac,
        vmin=vmin,
        vmax=vmax,
    )
    zero = {
        "pch": np.zeros((K, T)),
        "pdis": np.zeros((K, T)),
        "soc": np.tile((0.5*ess_caps_mwh)[:, None], (1, T+1)),
        "p_storage": np.zeros((K, T)),
    }
    return validate_schedule_ac(zero, pars)

# ---------------------------------------------------------------------
# Case study
# ---------------------------------------------------------------------
case1 = validate_no_ess_ac()

r2, i2, p2 = solve_dispatch(lambda_risk=0.0, beta=0.95)
case2 = validate_schedule_ac(extract_schedule(r2, i2), p2)

r3, i3, p3 = solve_dispatch(lambda_risk=0.9, beta=0.95)
case3 = validate_schedule_ac(extract_schedule(r3, i3), p3)

summary = pd.DataFrame([
    [
        "Case 1: no ESS",
        case1["expected_cost"],
        case1["cvar_cost"],
        case1["cvar_risk"],
        case1["violation_pu_h"],
        case1["vmin"],
        case1["peak_expected_import_mw"],
        case1["expected_loss_mwh"],
    ],
    [
        "Case 2: expected-value ESS",
        case2["expected_cost"],
        case2["cvar_cost"],
        case2["cvar_risk"],
        case2["violation_pu_h"],
        case2["vmin"],
        case2["peak_expected_import_mw"],
        case2["expected_loss_mwh"],
    ],
    [
        "Case 3: CVaR ESS",
        case3["expected_cost"],
        case3["cvar_cost"],
        case3["cvar_risk"],
        case3["violation_pu_h"],
        case3["vmin"],
        case3["peak_expected_import_mw"],
        case3["expected_loss_mwh"],
    ],
], columns=[
    "case",
    "expected economic cost",
    "CVaR economic cost",
    "CVaR network risk",
    "voltage violation p.u.-h",
    "minimum voltage",
    "peak expected import MW",
    "expected line loss MWh",
])

print("\nFull AC pandapower validation:")
print(summary.round(4).to_string(index=False))

fig, ax = plt.subplots(figsize=(10, 4))
for label, case in [
    ("Case 2 expected", case2),
    ("Case 3 CVaR", case3),
]:
    net_discharge = (case["pdis"] - case["pch"]).sum(axis=0)
    ax.step(hours, net_discharge, where="mid", label=label)
ax.axhline(0, linewidth=1)
ax.set_xlabel("Hour")
ax.set_ylabel("ESS net discharge power (MW)")
ax.grid(alpha=.25)
ax.legend()
plt.show()

fig, ax = plt.subplots(figsize=(10, 4))
for k, name in enumerate(["ESS@15", "ESS@32"]):
    ax.plot(np.arange(T+1), case2["soc"][k], marker="o", alpha=.7, label=f"{name} - Case2")
    ax.plot(np.arange(T+1), case3["soc"][k], marker="x", alpha=.9, label=f"{name} - Case3")
ax.set_xlabel("Hour boundary")
ax.set_ylabel("Stored energy (MWh)")
ax.grid(alpha=.25)
ax.legend(ncol=2)
plt.show()

crit_idx = crit_paper_buses - 1
worst2 = case2["vm"][:, :, crit_idx].min(axis=(0, 2))
worst3 = case3["vm"][:, :, crit_idx].min(axis=(0, 2))

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(hours, worst2, marker="o", label="Case 2 worst-scenario min V")
ax.plot(hours, worst3, marker="o", label="Case 3 CVaR worst-scenario min V")
ax.axhline(0.94, linestyle="--", label="0.94 p.u. reference")
ax.set_xlabel("Hour")
ax.set_ylabel("Minimum AC voltage (p.u.)")
ax.grid(alpha=.25)
ax.legend()
plt.show()

rows = []
for lam in [0.0, 0.25, 0.50, 0.75, 0.90]:
    rr, ii, pp_ = solve_dispatch(lambda_risk=lam, beta=0.95)
    ee = validate_schedule_ac(extract_schedule(rr, ii), pp_)
    rows.append([
        lam,
        ee["expected_cost"],
        ee["cvar_risk"],
        ee["violation_pu_h"],
        ee["vmin"],
        ee["expected_loss_mwh"],
    ])

sens_df = pd.DataFrame(rows, columns=[
    "risk weight λ",
    "expected cost",
    "CVaR network risk",
    "voltage violation p.u.-h",
    "minimum voltage",
    "expected line loss MWh",
])
print("\nRisk-weight sensitivity, scored by full AC power flow:")
print(sens_df.round(4).to_string(index=False))

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(
    sens_df["expected cost"],
    sens_df["CVaR network risk"],
    marker="o",
)
for _, row in sens_df.iterrows():
    ax.annotate(
        f"λ={row['risk weight λ']}",
        (row["expected cost"], row["CVaR network risk"]),
    )
ax.set_xlabel("Expected economic cost")
ax.set_ylabel("CVaR network risk")
ax.grid(alpha=.25)
plt.show()
