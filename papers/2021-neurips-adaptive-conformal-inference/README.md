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

## Executed SPS-UK results

The notebook has been executed end-to-end in GitHub Actions and the outputs are committed.

| Method | Coverage | Coverage error vs 90% | Local coverage RMSE | Mean finite width |
|---|---:|---:|---:|---:|
| Fixed alpha / raw score | 89.940% | 0.060% | 0.04121 | 0.96259 |
| ACI, gamma=0.005 / raw score | 89.995% | 0.005% | 0.02213 | 0.97983 |
| Fixed alpha / normalized score | 89.682% | 0.318% | 0.04274 | 0.88985 |
| ACI, gamma=0.005 / normalized score | 90.004% | 0.004% | 0.02003 | 1.17633 |

For the raw-score ACI run, final empirical miscoverage is **0.100054** versus the target **0.100000**. The numerical Proposition 4.1 check passes; the final absolute gap is **0.000054**, below the theoretical bound **0.008198**.

A simple six-block score-stability diagnostic gives a q90 coefficient of variation of **0.2202** for the raw residual score and **0.1791** for the normalized score. On this dataset the normalized score therefore has a more stable block-wise 90th percentile, although its ACI intervals are not narrower in this run.

Gamma sensitivity also shows the expected trade-off: larger gamma reduces local coverage RMSE but increases alpha volatility and can produce occasional infinite-width sets under the paper's theory-compatible boundary convention.
