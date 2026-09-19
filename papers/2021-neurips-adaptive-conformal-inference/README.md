# Gibbs & Candès (2021) — Adaptive Conformal Inference

Paper: **Adaptive Conformal Inference Under Distribution Shift**, NeurIPS 2021.

This folder contains a clean-room, method-level reproduction on the repository's existing SPS-UK demand data.

## Scope

This is not a numerical reproduction of the paper's original real-data experiments. The goal is to reproduce and inspect the mechanisms most relevant to later net-load work:

- fixed alpha vs adaptive alpha;
- long-run empirical miscoverage targeting;
- numerical verification of Proposition 4.1;
- gamma adaptability/stability trade-off;
- raw absolute residual vs normalized conformity score.

## Data

The notebook reuses:

`papers/2024-smartgridcomm-conformal-mlpf/data/SPS-UK_dataset.zip`

Only demand is used. The 30-minute series is resampled to hourly data, and a 24-hour seasonal persistence predictor is used to keep the forecasting model intentionally simple.

## Main settings

- target miscoverage: `alpha = 0.10`
- paper step size: `gamma = 0.005`
- rolling score/calibration window: 1250 observations
- local coverage window: 500 observations
- point forecast: `y_hat[t] = y[t-24]`

The implementation follows the paper's theory-compatible boundary convention and does not clip `alpha_t` to `[0,1]`.

## Notebook

- `Gibbs_Candes_2021_ACI_SPS_UK_reproduction.ipynb`

The notebook is executed in GitHub Actions and committed back with outputs.
