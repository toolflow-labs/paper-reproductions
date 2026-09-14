PYTHON ?= python

.PHONY: data experiment figures all smoke test clean

data:
	$(PYTHON) scripts/01_download_data.py --dataset sps-uk
	$(PYTHON) scripts/02_prepare_data.py --dataset sps-uk

experiment:
	$(PYTHON) scripts/03_run_experiments.py --dataset sps-uk

figures:
	$(PYTHON) scripts/04_plot_results.py --dataset sps-uk

all: data experiment figures

smoke:
	$(PYTHON) scripts/01_download_data.py --dataset sps-uk
	$(PYTHON) scripts/02_prepare_data.py --dataset sps-uk
	$(PYTHON) scripts/03_run_experiments.py --dataset sps-uk --quick
	$(PYTHON) scripts/04_plot_results.py --dataset sps-uk

test:
	pytest -q

clean:
	rm -rf results/sps-uk data/processed/sps-uk.parquet
