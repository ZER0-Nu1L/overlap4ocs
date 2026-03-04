# Reproducibility Guide

This repository has two layers for paper reproduction:

1. **Raw experiment execution** via matrix specs in `config/matrix/*.toml`
2. **Figure data preparation and plotting** via `scripts/prepare_simulation_data.py` and `scripts/simulation_fig.py`

## Prerequisites

```bash
uv sync --extra notebook
```

`--extra notebook` is required because figure scripts use `pandas`/`numpy`/`matplotlib`.

## End-to-End Workflow

### 1) Run matrix experiments

```bash
for matrix in \
  config/matrix/exp1.1-hd+bruck-1.toml \
  config/matrix/exp1.1-pair-1.toml \
  config/matrix/exp1.1-hd+bruck-2.toml \
  config/matrix/exp1.1-pair-2.toml \
  config/matrix/exp1.2-hd+bruck.toml \
  config/matrix/exp1.2-pair.toml \
  config/matrix/exp1.3-ar_rb.toml \
  config/matrix/exp1.3-a2a_pair.toml \
  config/matrix/exp1.3-a2a_bruck.toml \
  config/matrix/example_matrix_sweep_msg+k-B.toml \
  config/matrix/example_matrix_sweep_msg+Tr.toml; do
  PYTHONPATH=. uv run python scripts/matrix_runner.py --matrix "$matrix"
done
```

Smoke run:

```bash
PYTHONPATH=. uv run python scripts/matrix_runner.py \
  --matrix config/matrix/exp1.1-hd+bruck-1.toml --limit 1
```

### 2) Build notebook-ready merged CSVs

```bash
uv run python scripts/prepare_simulation_data.py --target all
```

This generates:
- `logs/results-exp1.1.csv`
- `logs/results-exp1.3-ar.csv`
- `logs/results-exp1.3-a2a.csv`
- `logs/results-exp1.3-a2a-9.csv`

### 3) Generate paper figures

Scripted path (recommended for CI/reproducibility):

```bash
uv run python scripts/simulation_fig.py --write-summary --output-dir figures/paper
```

This command generates:
- `exp1.1-rs-hd.pdf`, `exp1.1-ar-hd.pdf`, `exp1.1-a2a-bruck.pdf`, `exp1.1-a2a-pair.pdf`
- `exp1.2_ar_hd.pdf`, `exp1.2_a2a_bruck.pdf`, `exp1.2_a2a_pair.pdf`
- `exp1.3_ar.pdf`, `exp1.3_a2a_9.pdf`, `exp1.3_a2a_256.pdf`
- `exp2.1_impact_k.pdf`
- `exp2.2_impact_Treconf.pdf`

Notebook path (for interactive editing):

```bash
uv run jupyter notebook scripts/simulation_fig.ipynb
```

## Data Dependency Map

- **Exp 1.1**:
  - Matrix specs: `exp1.1-hd+bruck-{1,2}.toml`, `exp1.1-pair-{1,2}.toml`
  - Prepared CSV: `logs/results-exp1.1.csv`
  - Plot tool: `scripts/simulation_fig.py` or `scripts/simulation_fig.ipynb`
- **Exp 1.2**:
  - Matrix specs: `exp1.2-hd+bruck.toml`, `exp1.2-pair.toml`
  - CSV: `logs/matrix_results-exp1.2-hd+bruck.csv`, `logs/matrix_results-exp1.2-pair.csv`
  - Plot tool: `scripts/simulation_fig.py` or notebook
- **Exp 1.3**:
  - Matrix specs: `exp1.3-ar_rb.toml`, `exp1.3-a2a_pair.toml`, `exp1.3-a2a_bruck.toml`
  - Prepared CSV: `logs/results-exp1.3-ar.csv`, `logs/results-exp1.3-a2a*.csv`
  - Plot tool: `scripts/simulation_fig.py` or notebook  
    Note: historical `results-exp1.3-a2a-9.csv` may contain `p=8`; CLI script auto-falls back to available `(p,k,B)`.
- **Exp 2.x**:
  - Matrix specs: `example_matrix_sweep_msg+k-B.toml`, `example_matrix_sweep_msg+Tr.toml`
  - CSV: `logs/matrix_results-m32_sweep_msg+k-B.csv`, `logs/matrix_results-m32_sweep_msg+Tr.csv`
  - Plot tool: `scripts/simulation_fig.py` or notebook
