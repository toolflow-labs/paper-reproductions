# CVaR active-distribution-network reproduction

Paper: Shiwei Xia et al. (2025), *Source-network-load-storage collaborated two-stage power dispatch of active distribution network with conditional value-at-risk*, **International Journal of Electrical Power & Energy Systems**, 172, 111120.

DOI: `10.1016/j.ijepes.2025.111120`

## Current implementation

The reproduction now uses **pandapower** for the IEEE 33-bus network and full balanced AC power-flow calculations.

The main notebook is self-contained:

- `cvar_adn_reproduction.ipynb`

Reusable script versions are also kept:

- `scenario_setup.py`
- `dispatch_cvar.py`

## Method

The workflow is:

```text
forecast-error scenarios
    -> 1000 raw scenarios
    -> 20 representative scenarios
    -> pandapower AC power flow for every scenario-hour
    -> AC finite-difference sensitivities dV/dP_storage and dP_grid/dP_storage
    -> 24 h two-ESS stochastic/CVaR scheduling LP
    -> full pandapower AC validation of the selected schedules
```

This is more rigorous than the earlier hand-written LinDistFlow version. The final reported voltage, grid-import and line-loss metrics are obtained from `pandapower.runpp()`, not from LinDistFlow.

The optimization layer still uses SciPy/HiGHS because the paper couples 20 scenarios, 24 time steps, inter-temporal SOC constraints and CVaR. That multi-scenario, multi-period problem is not a single native pandapower `runopp()` call.

## Network and paper settings retained

- IEEE 33-bus benchmark via `pandapower.networks.case33bw()`
- 12.66 kV benchmark system
- WT: buses 17/32, 0.9 MW each
- PV: buses 21/24, 0.6 MW each
- ESS: bus 15, 1.8 MWh / 0.3 MW
- ESS: bus 32, 1.0 MWh / 0.2 MW
- 24 h, 1 h resolution
- 1000 uncertainty scenarios -> 20 representative scenarios
- paper-style Case 1 / Case 2 / Case 3 comparison
- CVaR tail-risk objective

## Data limitation

The paper does not publish the original WT/PV/load time series or official implementation. The reproduction therefore uses:

- the standard pandapower IEEE 33-bus network;
- paper-specified device placements/capacities;
- 24 h load/PV/WT baseline profiles reconstructed from the trend of Fig. 8;
- synthetic correlated forecast-error scenarios.

See `REPRODUCTION_NOTES.md` for all substitutions.

## Run

```bash
pip install -r requirements.txt
jupyter lab cvar_adn_reproduction.ipynb
```

or:

```bash
python dispatch_cvar.py
```

The GitHub Actions workflow `.github/workflows/execute-cvar-adn.yml` executes the notebook and commits the current outputs when the notebook or requirements change.
