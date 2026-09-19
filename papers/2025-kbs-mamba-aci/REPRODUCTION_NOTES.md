# Reproduction Notes

## Paper-specified elements

The paper explicitly specifies the following elements used here:

- short-term regional load forecasting;
- one-hour-ahead setting;
- two-layer stacked LSTM;
- 5 cells per LSTM layer in the reported best LSTM configuration;
- MSE + Adam;
- 9 epochs;
- batch size 24;
- learning rate 0.01;
- ACI conformity score based on absolute point-forecast residuals;
- target interval example with `alpha = 0.1` (90% coverage);
- online ACI update: `alpha[t+1] = alpha[t] + gamma * (alpha - err[t])`;
- `err[t]=1` for miscoverage and `0` otherwise;
- evaluation with coverage, mean interval width, CRPS, and Winkler score.

## Reproduction assumptions

The following are not claimed to be the paper's original implementation:

- SPS-UK replaces the unavailable Tamil Nadu dataset.
- SPS-UK 30-minute demand is averaged to hourly demand.
- Lookback is set to 24 hours because the LSTM input history length is not clearly reported.
- Chronological split is 65% Train / 15% Calibration / 20% Test.
- `gamma=0.01` because the paper does not report the numeric ACI learning rate.
- A numerical clip is applied to `alpha_t` to keep the empirical quantile well-defined.
- The PyTorch LSTM uses standard LSTM cell dynamics; ReLU is applied to the last hidden representation before the linear head.

## Why CRPS is omitted here

ACI as implemented in the paper section directly constructs a central prediction interval from calibration residual quantiles. A single interval does not uniquely define a full predictive CDF.

Because the paper does not fully specify how the ACI interval was converted into a complete predictive distribution for CRPS, this clean-room reproduction does not invent that missing step. Winkler score is retained because it is directly defined from the interval and target coverage.

## Purpose

This folder is intentionally a small bridge from:

`Static Split CP -> ACI`

to the later research workflow:

`multi-horizon net-load forecast -> horizon-wise ACI -> risk scenarios -> rolling BESS dispatch`.
