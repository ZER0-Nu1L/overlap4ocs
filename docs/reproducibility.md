# Reproducibility Guide

This repository has two layers for paper reproduction:

1. **Raw experiment execution** via matrix specs in `config/matrix/paper/*.toml`
2. **Figure data preparation and plotting** via `scripts/prepare_simulation_data.py` and `scripts/simulation_fig.py`

## Prerequisites

Install `uv` first if it is not already available in your environment. For installation options, see the repository [`README.md`](../README.md) or the official `uv` docs: <https://docs.astral.sh/uv/>.

```bash
uv sync --extra notebook
```

`--extra notebook` is required because figure scripts use `pandas`/`numpy`/`matplotlib`.


## Runtime Expectations

- Start with a smoke run (`--limit 1`) first; this is usually a few minutes.
- Full paper reproduction is workload-dependent and can range from tens of minutes to hours.
- Because a full reproduction can run for hours, avoid running it on a local laptop/workstation when possible; prefer a server or other long-lived machine.
- Solver branch-and-bound variance can cause runtime differences across hosts and runs.

## GitHub Actions Profiles

The repository includes three CI profiles under `.github/workflows/`:

- `ci-pr-smoke.yml`:
  - Trigger: `pull_request`, `push` to `main`
  - Scope: compile-check + single-instance run + matrix smoke (`--limit 1`)
  - Target runtime: short, used as merge gate
- `repro-lite.yml`:
  - Trigger: weekly schedule + manual
  - Scope: limited matrix subset across Exp1.1/1.2/1.3/2.x with resumability and heartbeat/progress files
  - Output: matrix CSVs, progress JSON, and per-run logs/metrics artifacts
- `repro-full.yml`:
  - Trigger: manual only (`workflow_dispatch`)
  - Scope: full matrix suite from this guide, then `prepare_simulation_data.py`, with optional figure generation to `figures/paper_reproduce`
  - Usage: long-running paper-grade reproduction (do not use as PR gate)

## End-to-End Workflow

Matrix config layout:
- `config/matrix/paper/`: matrix specs referenced by the paper reproducibility flow.
- `config/matrix/examples/`: additional templates and historical sweep variants.

### 1) Run matrix experiments

Smoke run (recommended first):

Use this first to validate the environment, script orchestration, and logging before starting the full paper reproduction.

```bash
PYTHONPATH=. uv run python scripts/matrix_runner.py \
  --matrix config/matrix/paper/exp1.1-hd+bruck-1.toml \
  --limit 1 \
  --resume \
  --heartbeat-sec 10
```

Full matrix experiments:

Because this can run for several hours, prefer running it on a server rather than a local machine.

```bash
for matrix in \
  config/matrix/paper/exp1.1-hd+bruck-1.toml \
  config/matrix/paper/exp1.1-pair-1.toml \
  config/matrix/paper/exp1.1-hd+bruck-2.toml \
  config/matrix/paper/exp1.1-pair-2.toml \
  config/matrix/paper/exp1.2-hd+bruck.toml \
  config/matrix/paper/exp1.2-pair.toml \
  config/matrix/paper/exp1.3-ar_rb.toml \
  config/matrix/paper/exp1.3-a2a_pair.toml \
  config/matrix/paper/exp1.3-a2a_bruck.toml \
  config/matrix/paper/exp2.1-matrix_sweep_msg+k-B.toml \
  config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml; do
  PYTHONPATH=. uv run python scripts/matrix_runner.py \
    --matrix "$matrix" \
    --resume \
    --rerun-failed \
    --heartbeat-sec 30
done
```

Resume/recovery recommendations:
- Keep `--resume` enabled (default) for long runs; avoid `--no-resume` unless intentionally rebuilding CSVs.
- Add `--rerun-failed` when restarting interrupted batches.
- Use `--limit N` for phased execution or smoke validation before full sweeps.
- Keep heartbeat logs visible with `--heartbeat-sec` (set `0` to disable).

Runtime observability:
- Matrix progress snapshots are written to `logs/repro/<matrix_id>_progress.json`.
- Quick status checks:
  - `wc -l logs/matrix_results-*.csv`
  - `tail -n 20 logs/repro/*_progress.json`

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

Important:
- `scripts/simulation_fig.py` overwrites files with the same name under `figures/paper/`.
- If you manually uploaded or curated files in `figures/paper/`, use a separate output directory, for example:

```bash
uv run python scripts/simulation_fig.py --write-summary --output-dir figures/paper_reproduce
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


## CI / Sandbox Reproducibility Notes

To reduce environment coupling in CI/sandbox environments:

- Prefer `uv sync --frozen` to keep dependencies pinned to `uv.lock`.
- Keep cache inside workspace (avoid HOME permission coupling):
  - `export UV_CACHE_DIR="$PWD/.uv-cache"`
- Use headless plotting backend:
  - `export MPLBACKEND=Agg`
- Keep matrix runs resumable:
  - `--resume --rerun-failed --heartbeat-sec 30`
- Preserve manually curated figures by writing to a separate output directory:
  - `--output-dir figures/paper_reproduce`

CI-friendly matrix command template:

```bash
export UV_CACHE_DIR="$PWD/.uv-cache"
export MPLBACKEND=Agg

PYTHONPATH=. uv run python scripts/matrix_runner.py \
  --matrix <config/matrix/paper/*.toml> \
  --resume --rerun-failed --heartbeat-sec 30
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
  - Prepared CSV:
    - `logs/results-exp1.3-ar.csv` (`p=256`, End-to-End Primitive Performance / AR): merged from
      - `exp1.3` recursive-doubling rows (`matrix_results-exp1.3-ar.csv`)
      - `exp1.1` halving-doubling rows filtered by `p=256, k=8, B=12.5, T_reconf=0.2, T_lat=0.02`
      - analytical baselines (`ar_ring`, `ar_dbt`, `ar_dbt_pipe`)
    - `logs/results-exp1.3-a2a.csv` (`p=256`, End-to-End Primitive Performance / A2A): merged from
      - `exp1.3` pairwise rows (`matrix_results-exp1.3-a2a.csv`)
      - `exp1.1` bruck rows filtered by `p=256, k=8, B=12.5, T_reconf=0.2, T_lat=0.02`
    - `logs/results-exp1.3-a2a-9.csv` (`p=9`): from `matrix_results-exp1.3-a2a-9.csv`
  - Plot tool: `scripts/simulation_fig.py` or notebook
  - Coupling rationale: reuse of compatible `exp1.1` baselines (`ar_having-doubling`, `a2a_bruck`) reduces duplicate compute and keeps cross-figure baseline consistency.
  - Correctness condition: if exp1.3 topology/runtime defaults change, regenerate compatible exp1.1 baseline rows (or switch to direct exp1.3 matrices at matching topology) before plotting.
- **Exp 2.x**:
  - Matrix specs: `exp2.1-matrix_sweep_msg+k-B.toml`, `exp2.2-matrix_sweep_msg+Tr.toml`
  - CSV: `logs/matrix_results-exp2.1-matrix_sweep_msg+k-B.csv`, `logs/matrix_results-exp2.2-matrix_sweep_msg+Tr.csv`
  - Plot tool: `scripts/simulation_fig.py` or notebook
