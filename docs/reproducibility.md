# Reproducibility Guide

This repository has two layers for paper reproduction:

1. **Raw experiment execution** via matrix specs in `config/matrix/paper/*.toml`
2. **Figure data preparation and plotting** via `scripts/prepare_simulation_data.py` and `scripts/simulation_fig.py`

## Prerequisites

Install `uv` first if it is not already available in your environment. For installation options, see the repository [`README.md`](../README.md) or the official `uv` docs: <https://docs.astral.sh/uv/>.

```bash
uv sync --extra notebook --python 3.12
```

`--extra notebook` is required because figure scripts use `pandas`/`numpy`/`matplotlib`.
Python 3.12 is the reference Python version used for the AE reproduction audit.
Python 3.10+ should work, but pinning 3.12 avoids host-dependent interpreter
selection by `uv`.


## Runtime Expectations

- Start with a smoke run (`--limit 1`) first; this is usually a few minutes.
- Full paper reproduction is workload-dependent and can range from tens of minutes to hours.
- For planning purposes, budget a full end-to-end paper reproduction conservatively as a multi-hour run; on a typical workstation or server, setting aside roughly 6-12 hours (or an overnight window) is a reasonable baseline.
- Because a full reproduction can run for hours, avoid running it on a local laptop/workstation when possible; prefer a server or other long-lived machine.
- Solver branch-and-bound variance can cause runtime differences across hosts and runs.

A simple worst-case planning estimate is:

```text
worst_case_solver_time <= number_of_runs * solver_time_limit
```

The full paper matrix suite below contains 298 planned runs under the default
paper configuration. With the default `solver_time_limit = 120` seconds:

```text
298 * 120s = 35,760s ~= 9.93h
```

This is a conservative solver-time upper bound, not an exact wall-clock runtime.
Many CBC runs finish before the time limit; setup, CSV preparation, and plotting add smaller overheads.

> [!NOTE]
> The estimate above is useful for planning the worst case under the default
> `solver_time_limit`, but actual wall-clock time is usually lower because CBC
> can terminate before the time limit when it finds a sufficient incumbent or
> closes the requested gap.

As a reference point, our post-AE full reproduction audit on an Intel Xeon Gold 6152 server (88 vCPUs, 125 GB RAM), Python 3.12.13, PuLP 3.3.0, and CBC 2.10.3 completed the full matrix/prepare/plot workflow in about **6.5 hours** and regenerated all 12 paper figure PDFs.

## Solver Budget and Platform Variance

SWOT uses an offline MILP scheduler. The paper fixes `solver_time_limit = 120`
seconds for all reported schedules unless explicitly stated otherwise, so the
paper matrix files keep that value for fair comparison. Time-limited MILP search
can produce different incumbent solutions across CPU models, thread counts, CBC
versions, operating systems, and wall-clock budgets. Such differences can change
the exact gain in a figure while preserving the main trend.

> [!IMPORTANT]
> Solver sensitivity is expected for the larger MILP instances. If your machine
> is substantially smaller than the reference server above, or if your CBC build
> uses fewer effective CPU threads, the default 120-second budget may produce a
> weaker incumbent for figures such as Fig. 9(a). In that case, increase
> `solver_time_limit` on a copied matrix file before comparing exact gains.

> [!TIP]
> Keep the checked-in paper matrices unchanged when reproducing the paper
> configuration. For platform-specific reruns, copy them first and change the
> solver budget in the copy.

If you are running on a smaller machine and want to spend more time searching,
copy the paper matrices and edit the copy rather than changing
`config/matrix/paper/*.toml` in place:

```bash
mkdir -p config/matrix/custom
cp config/matrix/paper/*.toml config/matrix/custom/
awk -i inplace '/solver_time_limit = / {$0="solver_time_limit = 300"} {print}' \
  config/matrix/custom/*.toml
```

Then run the same matrix workflow against `config/matrix/custom/*.toml`.

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

## Paper Figure Mapping

The scripted artifact pipeline regenerates the evaluation figures, not the
background/design diagrams. Design-intuition and topology figures in the paper
are static explanatory assets; the matrix workflow below is for the quantitative
evaluation figures.

| Paper figure | Generated PDF | Matrix inputs / CSV inputs |
| --- | --- | --- |
| Fig. 7(a) ReduceScatter | `exp1.1-rs-hd.pdf` | `exp1.1-hd+bruck-{1,2}.toml` -> `logs/results-exp1.1.csv` |
| Fig. 7(b) AllReduce | `exp1.1-ar-hd.pdf` | `exp1.1-hd+bruck-{1,2}.toml` -> `logs/results-exp1.1.csv` |
| Fig. 7(c) A2A Bruck | `exp1.1-a2a-bruck.pdf` | `exp1.1-hd+bruck-{1,2}.toml` -> `logs/results-exp1.1.csv` |
| Fig. 7(d) A2A Pairwise | `exp1.1-a2a-pair.pdf` | `exp1.1-pair-{1,2}.toml` -> `logs/results-exp1.1.csv` |
| Fig. 8(a) AllReduce scalability | `exp1.2_ar_hd.pdf` | `exp1.2-hd+bruck.toml` -> `logs/matrix_results-exp1.2-hd+bruck.csv` |
| Fig. 8(b) A2A scalability | `exp1.2_a2a_pair.pdf` | `exp1.2-pair.toml` -> `logs/matrix_results-exp1.2-pair.csv` |
| Fig. 9(a) All-to-All primitive envelope | `exp1.3_a2a_256.pdf` | `exp1.3-a2a_pair.toml` plus compatible `exp1.1-hd+bruck-2.toml` Bruck rows -> `logs/results-exp1.3-a2a.csv` |
| Fig. 9(b) AllReduce primitive envelope | `exp1.3_ar.pdf` | `exp1.3-ar_rb.toml` plus compatible `exp1.1-hd+bruck-2.toml` HD rows and analytical AR baselines -> `logs/results-exp1.3-ar.csv` |
| Fig. 10 optical degree sensitivity | `exp2.1_impact_k.pdf` | `exp2.1-matrix_sweep_msg+k-B.toml` |
| Fig. 11 reconfiguration-latency sensitivity | `exp2.2_impact_Treconf.pdf` | `exp2.2-matrix_sweep_msg+Tr.toml` |

For Fig. 9(a), the plotted primitive-level comparison intentionally combines
the `a2a_pairwise` p=256 matrix with compatible `a2a_bruck` rows from Exp. 1.1
at the same topology/runtime settings. This keeps the primitive envelope
comparison consistent without duplicating the Bruck run.

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


## Output Schema Quick Reference

Each `logs/matrix_results-*.csv` row records one matrix run. The most useful
columns are:

- `algorithm`, `message_mib`, `k`, `p`, `B`, `T_reconf`, `T_lat`
- `solver`, `solver_gap`, `solver_time_limit`
- `status`, `returncode`, `duration_seconds`
- `optimized_cct`, `baseline_cct`, `oneshot_cct`, `ideal_cct`
- `improvement_over_baseline_pct`, `metrics_path`

Per-run artifacts are stored under `logs/runs/<run-id>/`:

- `config/instance.toml` and `config/program.toml`: exact config snapshots
- `run.log`: stdout/stderr from `main.py` and the solver
- `metrics.json`: structured CCT and improvement values
- `solution/*.json`: generated schedules
- `figures/*.pdf`: per-run Gantt charts
