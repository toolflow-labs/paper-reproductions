# Reproduction notes

## Paper-specified structure retained

- Point forecasts are generated first, uncertainty is quantified afterward.
- Random Forest Regression is included as the main point-prediction backbone.
- M1: Basic CP.
- M2: CP with KNN uncertainty scalar.
- M3: CP with KNN scalar + Mondrian binning.
- M4: CPS with KNN.
- M5: CPS with KNN + Mondrian binning.
- KNN uses 50 neighbours in the full demo.
- Mondrian uses 15 equal-frequency bins in the full demo.
- Newsvendor uses the ratio between down- and up-regulation price deltas.
- Price scenarios are represented by 20 clusters in the full demo.
- EUM uses PV predictive scenarios and RTM price scenarios.
- EUM+CVaR uses a lower-tail profit risk term.
- Perfect information bids actual PV.
- Profit and imbalance are reported together.

## Clean-room substitutions

### Data

The paper uses aggregated hourly output from 175 PV systems in Utrecht together with ECMWF day-ahead weather forecasts, ENTSO-E DAM prices and TenneT regulation prices. This directory uses a deterministic synthetic Dutch-style data generator so CI does not depend on downloading several external historical sources.

### Train/calibration/test dates

The publication uses 2014–2015 for training, 2016 for calibration and 2017 for testing. The default synthetic data span four years and are split chronologically into equivalent 50% / 25% / 25% roles. Smoke mode uses a shorter series but preserves the same chronological split.

### CPS implementation

The paper uses conformal predictive systems and the crepes package. The clean-room implementation represents CPS as the empirical signed-residual distribution after KNN scale normalization, optionally conditional on Mondrian bin. This preserves the main distinction from symmetric absolute-residual CP: predictive quantiles may shift asymmetrically around the point forecast.

### EUM optimization

The appendix formulates EUM as an optimization problem. Because quantity bid is a scalar in [0,1] at each timestamp, this reproduction uses a dense one-dimensional grid search instead of introducing an LP/MILP dependency. The objective is the same economic mapping: DAM bid revenue plus surplus/deficit settlement under PV × RTM price scenarios.

### Runtime

The paper evaluates thousands of daylight timestamps. To keep the repository's automated test lightweight, the demo caps the number of decision-evaluation timestamps; forecast calibration still uses the full calibration partition.
