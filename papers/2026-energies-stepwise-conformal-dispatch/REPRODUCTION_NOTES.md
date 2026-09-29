# Reproduction notes

## Paper-specified facts retained

- Time resolution: 15 min.
- Historical lookback: 96 steps = 24 h.
- Forecast horizons: 4 and 16 steps for 1 h and 4 h.
- Nominal interval: 90%.
- Stepwise CQR score: `max(lower-y, y-upper, 0)`.
- One calibration correction per forecast step.
- PV-ramping volatility grouping is based on physical PV ramps, not forecast errors.
- Rolling-dispatch comparison uses perfect information / median forecast / calibrated upper bound.

## Clean-room substitutions

### Data

The paper reports an eastern-China microgrid with 15 PV units (52.1 MW) and 2 storage units (61 MW / 123 MWh), but the chronological data are not published. The runnable demo therefore uses a deterministic synthetic high-PV series with the same 15-min granularity and roughly comparable PV scale.

### Forecast model

The publication specifies a multi-quantile forecasting framework and pinball loss but does not provide enough architecture detail for an author-faithful implementation. The reproduction uses scikit-learn histogram gradient boosting independently for each horizon and quantile.

### Conformal quantile convention

The code uses the finite-sample split-conformal `higher` quantile convention

`ceil((n+1)*coverage)/n`.

This makes the intended 90% coverage explicit and avoids ambiguity in the paper's notation, where `alpha` is used in places as a confidence level rather than a miscoverage probability.

### Dispatch objective

The paper does not publish a complete mathematical optimization model for Table 6. The reproduction therefore uses a transparent LP with purchase cost, peak penalty, storage energy recursion and power/energy bounds. The purpose is to reproduce the information interface (`actual` vs `median` vs `calibrated upper`) rather than the paper's reported CNY values.
