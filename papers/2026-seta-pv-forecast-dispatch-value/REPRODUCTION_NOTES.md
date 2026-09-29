# Reproduction notes

## Paper-specified parts retained

- 15 min dispatch resolution.
- 60 min-ahead PV commitment is the dispatch-relevant forecast horizon.
- Daily 96-step LP.
- Battery commitment is forecast-dependent.
- In ex-post recourse the battery commitment is held fixed; grid exchange, curtailment and ENS absorb realized PV error.
- Realized end-of-day SOC is carried to the next day.
- Persistence and perfect forecast are evaluated under the same operating boundary.
- Central parameters follow Table 1 of the paper.
- Quantile commitment scan uses q0.1–q0.9.
- Fixed-commitment recourse boundary varies import capacity and VOLL.
- Islanded stress test is treated separately and re-optimizes commitment.
- Value capture ratio and value capture gap follow the paper's Eqs. (19)–(22).

## Clean-room substitutions

### Data

The paper uses DKP/DKA Solar Centre field measurements plus NASA POWER variables. This runnable skeleton uses a deterministic synthetic DKP-like PV/load series. It is intended to validate the decision-value machinery, not reproduce the paper's AUD totals.

### Forecast models

The original study compares LightGBM, linear quantile regression, kNN and random forest. The present skeleton deliberately does not reproduce those model families. It generates persistence, a transparent noisy point forecast and a heteroscedastic q0.1–q0.9 grid so that the dispatch/value layer can be exercised independently.

The authors' public repository should be used if exact model-level numerical reproduction becomes necessary.

### Commitment ENS variable

The central paper commitment balance is written without ENS because the central grid-connected case has ample recourse. The clean-room LP keeps an ENS slack variable in the commitment formulation so that the same solver remains feasible for constrained and islanded stress cases. With ample central import capacity it is economically dominated by grid supply.

## What this skeleton is for

This directory is designed to receive forecast trajectories from other folders. In particular, fixed CP, horizon-wise ACI and CVaR-derived BESS actions can all be evaluated under the same persistence/perfect-information value anchors.
