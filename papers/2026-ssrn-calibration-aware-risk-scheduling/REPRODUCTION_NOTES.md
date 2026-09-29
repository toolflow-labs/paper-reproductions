# Reproduction notes

## Paper-specified settings retained

- Lookback 24 h; forecast horizon 24 h.
- Two targets: EV charging load and PV output.
- Seven quantile levels: 0.05/0.10/0.25/0.50/0.75/0.90/0.95.
- Encoder-decoder Transformer.
- Cumulative-softplus output head for noncrossing quantiles.
- Pinball loss and chronological 60/10/15/15 split.
- Independent calibration set.
- Posterior interval calibration before scenario generation.
- AR(1) dependence across consecutive horizons.
- Gaussian Copula dependence between EV and PV.
- 100 scenarios in the full configuration.
- CVaR-based risk-adjusted net load.
- BESS: 100 kWh, 50 kW, charge/discharge efficiency 0.95, SOC 10%-100%.

## Clean-room assumptions / gaps in the preprint

### Public-data materialization

The paper names ACN-Data, NASA POWER/pvlib and CAISO NP15, but does not publish one frozen dataset corresponding exactly to its reported experiment. The runnable demo therefore uses a deterministic surrogate. The model/data boundary is deliberately isolated so a later data materializer can replace it.

### Interval scaling

The text reports interval scaling before CQR but does not specify the optimization or formula. The reproduction fits the smallest symmetric multiplicative scale around the median that reaches nominal calibration coverage for each horizon and target.

### Full calibrated marginal distribution

CQR formally calibrates an interval, not an entire seven-quantile CDF. For scenario sampling, this implementation scales all quantile deviations around the median and then tapers the CQR boundary correction linearly from zero at q50 to the full correction at q05/q95. Monotonicity is re-enforced with `maximum.accumulate`.

### Copula parameters

The preprint states AR(1) + Gaussian Copula but does not publish the fitted coefficients. They are estimated from calibration-set median residuals: adjacent-horizon residual correlation for each target and same-horizon EV/PV residual correlation for the copula.

### Stochastic comparator

The paper compares with two-stage stochastic linear programming but omits enough formulation detail that an exact clean-room reconstruction would require additional assumptions. `optimize_stochastic()` is therefore labelled a scenario-embedded stochastic proxy: one common BESS schedule is optimized against scenario-specific grid imports.
