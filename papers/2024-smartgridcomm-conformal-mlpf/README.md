# Conformal-MLPF reproduction (SmartGridComm 2024)

Clean-room reproduction of:

> Anthony Faustine and Lucas Pereira, **Conformal Multilayer Perceptron-Based Probabilistic Net-Load Forecasting for Low-Voltage Distribution Systems with Photovoltaic Generation**, IEEE SmartGridComm 2024, pp. 59–64. DOI: 10.1109/SmartGridComm60555.2024.10738106.

The paper turns a deterministic MLP net-load forecast into prediction intervals with Split Conformal Prediction (SCP), and compares it with MLP quantile regression and Monte-Carlo dropout.

## What this folder reproduces

The pipeline is intentionally end-to-end:

1. Download the public Plymouth / SPS-UK demand, PV, and weather data from Zenodo record `5500457`.
2. Align data to 30-minute resolution and construct net load = demand - PV.
3. Build lagged historical inputs, future weather/time covariates, and 48-step targets.
4. Train the deterministic dual-encoder MLP point forecaster.
5. Calibrate horizon-wise Split Conformal intervals from held-out calibration residuals.
6. Train MLP-QR and MLP-MCD baselines.
7. Evaluate NRMSE, PICP, NMPI and a clearly-labelled CWE proxy.
8. Produce paper-style interval plots and comparison tables.

## Important reproducibility note

This is a **clean-room reproduction, not the authors' original SmartGridComm source code**. The six-page paper specifies the major architecture/training choices but leaves some details implicit or delegated to earlier work. Those gaps are documented in `REPRODUCTION_NOTES.md` rather than silently guessed.

The paper reports two datasets, MLVS-PT (Madeira) and SPS-UK (Plymouth). The public SPS-UK raw files are automatically downloadable. The paper says SPS-UK weather comes from MERRA-2; the Zenodo record also contains an hourly reanalysis weather file. This repository uses the Zenodo weather file by default so the pipeline is runnable without credentials, and supports a user-supplied MERRA-2 CSV override. This difference means exact Table I numbers should not be expected from the default public-data run.

MLVS-PT is supported if `data/raw/mlvs_pt/MLVS-PT.parquet` is supplied. The paper does not provide a stable public download URL for that file.

## Quick start

```bash
cd papers/2024-smartgridcomm-conformal-mlpf
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

make data
make experiment
make figures
```

Or run everything:

```bash
make all
```

For a fast plumbing check:

```bash
make smoke
```

## Commands

```bash
python scripts/01_download_data.py --dataset sps-uk
python scripts/02_prepare_data.py --dataset sps-uk
python scripts/03_run_experiments.py --dataset sps-uk
python scripts/04_plot_results.py --dataset sps-uk
```

To use a MERRA-2 export instead of the bundled Zenodo weather file:

```bash
python scripts/02_prepare_data.py --dataset sps-uk \
  --weather-override /path/to/merra2_halfhourly.csv
```

The override should contain a timestamp column plus at least one temperature-like column and one radiation/irradiance-like column.

## Outputs

After a run:

```text
results/sps-uk/
├── metrics.csv
├── fold_predictions.npz
└── figures/
    ├── prediction_intervals.png
    └── metrics_comparison.png
```

## Paper-specified settings retained here

- 30-minute sampling for SPS-UK.
- Multi-horizon forecasting with `H=48` half-hours by default.
- Two hidden layers with 256 units and SiLU activation.
- Adam optimizer, initial learning rate `1e-3`.
- Learning-rate reduction at 75% and 90% of training.
- Mixed L1/L2 deterministic loss.
- 10-fold expanding-window backtesting concept.
- Last 10% of each training window reserved for conformal calibration.
- Horizon-wise conformal scores / intervals.
- Absolute-residual and signed-residual interval experiments.
- QR and MC-dropout probabilistic baselines.

See `REPRODUCTION_NOTES.md` for every deliberate assumption and deviation.

## Data provenance

SPS-UK public data:

- Zenodo: https://zenodo.org/records/5500457
- DOI: https://doi.org/10.5281/zenodo.5500457
- License stated by the record: Western Power Distribution Open Data Licence; Zenodo currently also displays CC BY 4.0 metadata.

The downloader fetches only the CSV files required by the experiment and does not commit the raw data to git.
