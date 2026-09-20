# CVaR active-distribution-network reproduction

Paper: Shiwei Xia et al. (2025), *Source-network-load-storage collaborated two-stage power dispatch of active distribution network with conditional value-at-risk*, **International Journal of Electrical Power & Energy Systems**, 172, 111120.

DOI: `10.1016/j.ijepes.2025.111120`

## Scope

This is a **method-level clean-room reproduction**, not an exact numerical reproduction. It focuses on the paper's core chain:

`forecast-error scenarios -> scenario reduction -> IEEE 33-bus -> ESS schedule -> CVaR tail risk -> risk-averse dispatch`

The original paper reports MATLAB + YALMIP + GUROBI and does not publish the full input data or implementation. The reproduction therefore keeps paper-specified placements/capacities and the CVaR mechanism, while making transparent substitutions where inputs are unavailable.

## Files

- `cvar_adn_reproduction.ipynb` — notebook entry point.
- `scenario_setup.py` — IEEE 33-bus data, 24 h profiles, correlated scenario generation/reduction, LinDistFlow voltage setup.
- `dispatch_cvar.py` — ESS sequence optimization, CVaR linearization, Case 1/2/3 comparison and risk-weight sensitivity.
- `REPRODUCTION_NOTES.md` — paper-specified settings vs. reproduction assumptions.
- `requirements.txt` — Python dependencies.

## Run

```bash
pip install -r requirements.txt
python dispatch_cvar.py
```

or open `cvar_adn_reproduction.ipynb` in Jupyter.

## Expected qualitative result

The reproduction is designed to recover the paper's central direction:

- adding ESS reduces expected operating cost/peak import relative to no ESS;
- adding the CVaR tail-risk term can slightly increase expected economic cost;
- in exchange, the worst-tail voltage-risk metric falls and the minimum-voltage margin improves.

With the fixed reproduction seed/settings, the expected-value ESS case has minimum voltage around **0.9371 p.u.**, while the CVaR case raises it to about **0.9400 p.u.**, with a small expected-cost premium.

See `REPRODUCTION_NOTES.md` before comparing these numbers with the paper's Tables 4–6.
