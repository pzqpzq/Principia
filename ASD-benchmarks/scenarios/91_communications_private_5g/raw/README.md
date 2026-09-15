# Measurement Dataset and Analysis Code

Data and code underlying **"Measurement-Driven Modeling of End-to-End Latency in an Indoor
Private Standalone 5G Network"** (MDPI *Network*, 2026).

Measurements were carried out in the private standalone 5G network of the TU Wien IFT
TEC-Lab.

---

## Contents

### `data/`: processed datasets

| File | Content |
|---|---|
| `latency_210.csv` | Per-trial one-way latency used for model fitting (210 runs) |
| `latency_with_achieved_bw_210.csv` | Latency joined with the achieved throughput predictor |
| `achieved_bandwidth_210.csv` | Achieved throughput parsed from the raw iPerf server reports |
| `latency_trials_raw_210.csv` | Full per-trial summary: achieved throughput, mean/min/max delay, standard deviation, jitter, loss, out-of-order counts, date, validity flag |
| `bandwidth_trials_tcp_35.csv` | Per-trial TCP throughput summary (35 runs) |
| `stage5_trial_level.csv` | Trial-level latency, jitter and loss statistics |
| `stage5_cell_summary.csv` | Per location–rate cell summary (42 cells) |
| `table3_trial_latency_summary.csv` | Median and P95 of trial-level mean latency (Table 3) |
| `table3_trial_latency_bootstrap_ci.csv` | Stratified-bootstrap 95 % confidence intervals (Table 3) |
| `table3_jitter_summary.csv` | Mean jitter by target rate (Table 3) |
| `table3_packet_loss_summary.csv` | Packet-loss statistics by target rate (Table 3) |
| `table3_maximum_delay_summary.csv` | Per-trial maximum delay by target rate (Table 3) |
| `fig5b_threshold_exceedance.csv` | Threshold-exceedance proportions with Wilson intervals (Figure 5b) |

### `raw/`: unmodified iPerf output

| File | Content |
|---|---|
| `raw_latency_logs.zip` | 210 UDP client logs (7 locations × 6 target rates × 5 repetitions) |
| `raw_throughput_logs.zip` | 35 TCP client logs (7 locations × 5 repetitions) |

Files are UTF-16 encoded plain text as written by iPerf on Windows.

### `code/`: MATLAB R2025b analysis pipeline, in execution order

| Script | Produces |
|---|---|
| `01_parse_achieved_bandwidth.m` | Achieved throughput parsed from the raw logs |
| `02_fit_model.m` | Fit of the proposed model (Table 4) |
| `03_cross_validate.m` | Trial-based train/test and leave-one-location-out validation (Table 5) |
| `04_bootstrap_ci.m` | Cell bootstrap, 1000 replicates (Table 4 confidence intervals) |
| `05_tail_jitter_stats.m` | Jitter, tail latency and packet-loss statistics (Table 3) |
| `06_gamma_bandwidth_corr.m` | Location offsets vs. location-specific throughput variability (Section 5.2) |
| `07_metallic_flag.m` | Metallic-environment indicator model (Section 5.2) |
| `08_baseline_comparison.m` | Baseline models and location-term ablation (Table 5) |
| `09_urllc_supplementary.m` | Empirical CDFs and threshold exceedance (Section 3.3, Figure 5) |
| `10_imputation_sensitivity.m` | Sensitivity analysis for the three replaced runs (Section 4.3.1) |

`code/figures/` contains the figure-generation scripts.

`code/python/` contains an independent re-implementation used to verify the published
parameter estimates without MATLAB:

| Script | Purpose |
|---|---|
| `refit_all_models.py` | Refits all five compared models and reproduces Table 5 |
| `robustness_and_bootstrap.py` | Imputation robustness check and bootstrap intervals |
| `verify_optimizer_settings.py` | Confirms that the reported optimizer settings reproduce the published estimates |

---

## Measurement summary

- **Tool:** iPerf 2.2.1, enhanced-report mode (`-e`), 60 s per run, 1 s reporting interval
- **Latency:** UDP, 1470-byte datagrams, 7 locations × 6 target rates (1, 10, 50, 100, 200,
  500 Mbps) × 5 repetitions = 210 runs
- **Throughput:** TCP, 7 locations × 5 repetitions = 35 runs
- **Campaign dates:** latency 27 June – 3 July 2025; throughput 3 June, 27 June and
  1 July 2025
- **Measurement points:** seven fixed indoor locations, each directly beneath one of the
  seven pico radio units of the deployment
- **Path measured:** complete end-to-end path between a wired campus host and a 5G-attached
  endpoint, including campus routing and firewall functions, the private 5G core and radio
  access network, the customer premises equipment, and the IEEE 802.11ax link between the
  CPE and the receiving host
- Models are fitted using the **achieved** throughput reported by iPerf, not the configured
  target rate

---

## Known data issue

Three runs (location Q1, 50 Mbps, repetitions 3–5) returned invalid one-way delay values
caused by a 32-bit counter wrap-around arising from residual clock offset between the two
hosts. These runs are flagged by `valid_owd = 0` in `data/latency_trials_raw_210.csv` and
were replaced by the cell mean in `data/latency_210.csv`. Script
`10_imputation_sensitivity.m` quantifies the effect: the model parameters change by less
than 4.4 % and the mean absolute error by 0.02 ms. See Section 4.3.1 of the article.

---

## Requirements

**MATLAB pipeline**, the analysis reported in the article (`code/`, `code/figures/`):

- MATLAB **R2025b** with the Optimization Toolbox (`lsqcurvefit`); no other toolboxes
  are used
- Known to work on Windows 10 and Windows 11

**Python verification scripts** (`code/python/`), an optional and independent re-implementation
that reproduces the reported parameter estimates without MATLAB:

- Tested with **Python 3.14.6** on Windows 11, using both **NumPy 2.4.6** and
  **NumPy 2.5.2**; results agree between the two NumPy versions to at least six
  significant figures
- NumPy is the only third-party dependency; everything else is from the standard library.
  See `code/python/requirements.txt`
- From `code/python/`, run:

      python -m pip install -r requirements.txt    # only if NumPy is missing
      python refit_all_models.py
      python robustness_and_bootstrap.py
      python verify_optimizer_settings.py

  All paths are resolved relative to the script location, so the archive can be extracted
  anywhere.

---

## Citation

This dataset is archived in the TU Wien Research Data repository:
https://doi.org/10.48436/hja53-s8y18 (DOI: 10.48436/hja53-s8y18).

When using these data, please cite both the dataset and the associated article.

---

## License

This record is dual-licensed:

| Part | Contents | License |
|---|---|---|
| **Data** | `data/`, `raw/`, this README | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| **Code** | `code/`: all MATLAB `.m` and Python `.py` scripts | MIT License |

Creative Commons licenses are not intended for software, so the analysis code carries a
dedicated software license. See `LICENSE.md` in the record, or `LICENSE-MIT.txt` inside
`code.zip`, for the full license texts.
