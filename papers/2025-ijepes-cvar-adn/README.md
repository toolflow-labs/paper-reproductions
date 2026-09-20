# CVaR active-distribution-network reproduction

Paper: Shiwei Xia et al. (2025), *Source-network-load-storage collaborated two-stage power dispatch of active distribution network with conditional value-at-risk*, **International Journal of Electrical Power & Energy Systems**, 172, 111120.

DOI: `10.1016/j.ijepes.2025.111120`

## Scope

This is a **method-level clean-room reproduction**, not an exact numerical reproduction.

The main artifact is the **self-contained** `cvar_adn_reproduction.ipynb`: the full scenario-generation, IEEE 33-bus setup, CVaR formulation, ESS dispatch optimization, Case 1/2/3 comparison, and sensitivity experiment are visible directly in notebook cells. It no longer hides the implementation behind a single `%run` cell.

## Data used

No public raw dataset was released with the paper. This reproduction therefore uses:

- the standard IEEE 33-bus / MATPOWER `case33bw` network data;
- paper-specified WT/PV/ESS placements and capacities;
- 24 h load/PV/WT baseline curves reconstructed from the trend of the paper's Fig. 8;
- synthetic correlated forecast-error scenarios generated from those baselines (1000 raw scenarios → 20 representative scenarios).

See `REPRODUCTION_NOTES.md` for the exact boundary between paper-specified settings and reproduction assumptions.

## Files

- `cvar_adn_reproduction.ipynb` — **complete self-contained notebook**.
- `scenario_setup.py` — same scenario/network setup extracted as a reusable script.
- `dispatch_cvar.py` — same CVaR/ESS dispatch experiment extracted as a reusable script.
- `REPRODUCTION_NOTES.md` — assumptions and deviations from the paper.
- `requirements.txt` — Python dependencies.

## Run

```bash
pip install -r requirements.txt
jupyter lab cvar_adn_reproduction.ipynb
```

or run the script form:

```bash
python dispatch_cvar.py
```

## Expected qualitative result

The intended reproduction target is the paper's central direction:

- ESS reduces expected operating cost / peak import relative to no ESS;
- adding the CVaR tail-risk term can slightly increase expected economic cost;
- in exchange, tail voltage-risk metrics improve.

This repository does **not** claim exact reproduction of Tables 4–6 because the paper does not publish all original inputs or official code.
