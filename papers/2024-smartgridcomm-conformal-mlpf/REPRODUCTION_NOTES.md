# Reproduction notes

This document distinguishes what is explicit in the 2024 SmartGridComm paper from what must be reconstructed.

## Paper-specified

- Deterministic MLPF followed by Split Conformal Prediction.
- Forecast horizon is multi-step; the paper evaluates 30-minute net-load series and constructs an interval for each horizon step.
- Conformity scores include absolute residuals `|y - y_hat|` and signed residuals `y - y_hat`.
- MLP uses two hidden layers, 256 nodes per layer, SiLU activation, Adam optimizer, initial learning rate 0.001, and learning-rate reductions by a factor of 0.1 at 75% and 90% of training.
- Deterministic loss mixes L1 and L2 errors.
- Evaluation uses expanding-window backtesting, starting with at least 12 months of history and a fixed 6-month future evaluation window, moving forward by 3 months.
- Within each fold, 90% of the pre-test data are used for model training and 10% for conformal calibration.
- Baselines: MLP quantile regression and MLP Monte-Carlo dropout.
- Metrics: NRMSE, PICP, NMPI, CWE.

## Derived directly from equations

For absolute-residual SCP, calibration is implemented horizon-wise:

`score[i, h] = abs(y_cal[i, h] - yhat_cal[i, h])`

and the finite-sample conformal quantile is the `ceil((n + 1) * (1 - alpha))` order statistic, clipped to the calibration sample size. The interval is:

`[yhat_test[:, h] - q[h], yhat_test[:, h] + q[h]]`.

## Explicit assumptions / deviations

1. **Exact MLPF internal architecture**: the conference paper refers readers to earlier work and shows two encoders for historical and future covariates. This reproduction implements two MLP encoders, sums their latent representations, and uses a direct multi-horizon decoder. It does not claim byte-for-byte equivalence to the authors' original implementation.
2. **RoPE details**: the paper diagram includes RoPE/LayerNorm but does not provide enough implementation detail in the conference paper to reconstruct exact tensor semantics. This clean-room implementation keeps LayerNorm and the dual-encoder structure but does not invent an undocumented RoPE implementation.
3. **L1/L2 mixing coefficient**: the paper defines `lambda` but does not state the final selected value in the six-page manuscript. Default is `0.5` and is configurable.
4. **Signed-residual intervals**: Eq. (9) defines signed residuals, but the paper does not fully specify the two-sided interval construction. We therefore implement an explicit equal-tail empirical signed-residual interval. Results are labelled `conformal_signed` and should be treated as a transparent reconstruction rather than an exact code match.
5. **CWE**: the paper gives the harmonic-mean form in terms of transformed coverage/width quantities but the conference paper does not fully define those transformations. We report `CWE_proxy`, a documented harmonic mean of a coverage-calibration score and a normalized sharpness score. It is not presented as an exact reproduction of the paper's CWE values.
6. **SPS-UK weather**: the paper states that MERRA-2 weather was used and interpolated to 30 minutes. The public Zenodo dataset also ships an hourly reanalysis weather file but does not identify it as the exact MERRA-2 extraction used by the paper. The default runnable pipeline uses that public weather file. A `--weather-override` option supports a user-provided MERRA-2 export.
7. **MLVS-PT**: no stable raw-data download URL is specified by the paper. The loader supports the parquet layout used in the authors' later public Twiga tutorials (`timestamp`, `NetLoad(kW)`, `Ghi`, `Temperature`) when the file is supplied locally.

## Interpretation of results

The goal of the initial PR is to reproduce the **methodological pipeline** and make all deviations auditable. Exact numerical reproduction of Table I requires the authors' exact preprocessing, MERRA-2 extraction, MLPF implementation, hyperparameters, and MLVS-PT file.
