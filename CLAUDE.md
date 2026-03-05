# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`overlap4ocs` (SWOT Scheduler) is a research codebase that jointly optimizes Optical Circuit Switch (OCS) reconfiguration with collective communication scheduling to minimize Communication Completion Time (CCT). The project formulates the problem as a Mixed Integer Linear Programming (MILP) model and solves it using commercial (Gurobi) or open-source (PuLP/COPT) solvers.

## Development Environment Setup

### Using uv (Recommended)

```bash
# Install uv (macOS)
brew install uv

# Create and sync virtual environment
uv sync

# With optional Gurobi support
uv sync --extra gurobi

# With notebook support (for Jupyter notebooks)
uv sync --extra notebook
```

### Using pip (Alternative)

```bash
pip install -r requirements.txt
```

## Running the Code

### Single Instance Execution

Run a single optimization instance:

```bash
# Using uv
uv run python main.py --config config/instance.toml

# Using pip
python3 main.py --config config/instance.toml
```

With metrics logging:

```bash
uv run python main.py --config config/instance.toml \
  --metrics-file logs/runs/demo_run_metrics.json \
  --run-id demo-run
```

### Batch Matrix Experiments

For systematic parameter sweeps:

```bash
# 1. Generate configurations from matrix spec
PYTHONPATH=. uv run python scripts/generate_matrix_configs.py \
  --matrix config/matrix/examples/example_matrix_sweep_msg+k.toml

# 2. Run the experiment matrix
PYTHONPATH=. uv run python scripts/matrix_runner.py \
  --matrix config/matrix/examples/example_matrix_sweep_msg+k.toml \
  --resume \
  --rerun-failed \
  --heartbeat-sec 30
```

Matrix runner options:
- `--limit N`: Run only N configs per pass
- `--resume` / `--no-resume`: Reuse or ignore existing matrix CSV state
- `--rerun-failed`: Re-execute previously failed runs
- `--heartbeat-sec N`: Print periodic liveness/progress updates while each run is solving
- `--progress-file <path>`: Persist live run status as JSON (default: `logs/repro/<matrix_id>_progress.json`)
- `--extra-args "..."`: Forward arguments to main.py
- `--dry-run`: Create run folders without executing

Paper figure output note:
- `scripts/simulation_fig.py --output-dir figures/paper` overwrites files with the same names.
- If `figures/paper` contains manually uploaded figures, write to a separate directory (for example `figures/paper_reproduce`).

Recommended restart flow for long paper runs:
1. Start with `--limit 1` smoke run.
2. Run full matrix with `--resume --rerun-failed`.
3. If interrupted, rerun the exact same command; completed hashes will be skipped.
4. Track progress via heartbeats and `logs/repro/<matrix_id>_progress.json`.

### Running Scripts

Scripts in `scripts/*.py` require the repository root in PYTHONPATH:

```bash
PYTHONPATH=. uv run python scripts/<script>.py --help
```

## Core Architecture

### Entry Point & Control Flow

**main.py**: Primary entry point with this execution flow:
1. Parse command-line arguments and load configuration
2. Compute **baseline** schedule (naive intra-collective reconfiguration)
3. Compute **one-shot** schedule (single OCS configuration for entire collective)
4. Compute **ideal** lower bound (theoretical minimum CCT)
5. Build and solve **MILP model** with optional warm start from baseline/one-shot
6. Extract results, validate, and generate Gantt chart visualizations
7. Write metrics and solution files

### Configuration System

Two-level configuration:

1. **Instance config** (`config/instance.toml`): Problem parameters
   - `solver`: "gurobi", "pulp", or "copt"
   - `k`: Number of OCS switches
   - `p`: Number of compute nodes
   - `m`: Message size (MB)
   - `B`: Bandwidth per link (GBps)
   - `T_reconf`: Reconfiguration delay (ms)
   - `T_lat`: End-to-end base latency (ms)
   - `algorithm`: Collective algorithm (e.g., "ar_having-doubling", "a2a_pairwise", "a2a_bruck")
   - `solver_gap`: Relative MIP gap tolerance (optional)
   - `solver_time_limit`: Solver time limit in seconds (optional)

2. **Program config** (`config/program.toml`): Runtime behavior
   - `save_as_pdf`: Whether to save Gantt charts
   - `debug_mode`: 0 (off), 1 (debug model), 2 (comparison mode)
   - `show`: Display charts interactively

**Units convention**: Time in milliseconds (ms), bandwidth in GBps, message size in MB. This allows direct calculation of transmission times as `m/B`.

### Paradigm Implementations

Located in `paradigm/`:

- **baseline.py**: Naive scheduling with intra-collective reconfiguration
- **one_shot.py**: Single OCS configuration for the entire collective (may be infeasible)
- **ideal.py**: Theoretical lower bound calculation
- **model_gurobi.py**: MILP formulation using Gurobi Python API
- **model_pulp.py**: MILP formulation using PuLP (supports PuLP native, PuLP+Gurobi backend, COPT)
- **warm_start.py**: Applies baseline/one-shot solutions as warm start for MILP
- **solver_wrapper.py**: Unified interface abstracting Gurobi/PuLP/COPT solver differences

Key functions in solver_wrapper:
- `solve_model()`: Solve with optional warm start and solver parameters
- `get_solution_value(var)`: Unified variable value extraction across solvers
- `write_model()`: Write solution to file (Gurobi .sol format or JSON for PuLP/COPT)
- `load_and_validate_solution()`: Load and validate solution against constraints

### Collective Communication Algorithms

**config/cc_algorithm.py** computes algorithm-specific parameters:
- Number of communication steps (`num_steps`)
- Message size per step (`m_i`)
- Required OCS configuration per step (`configurations`)

Supported algorithms:
- **AllReduce**: "ar_ring", "ar_having-doubling", "ar_recursive-doubling"
- **AllGather**: "ag_having-doubling"
- **ReduceScatter**: "rs_having-doubling"
- **AllToAll**: "a2a_pairwise", "a2a_bruck"

### MILP Model Structure

The mathematical model is documented in `docs/math_model.md`. Key decision variables:
- `d[i,j]`: Data volume assigned to OCS j at step i
- `u[i,j]`: Binary indicator if OCS j is used at step i
- `r[i,j]`: Binary indicator if OCS j is reconfigured at step i
- `t_start[i,j]`, `t_end[i,j]`: Transmission start/end times
- `t_reconf_start[i,j]`, `t_reconf_end[i,j]`: Reconfiguration start/end times
- `t_step_end[i]`: Step i completion time
- `cct`: Communication Completion Time (objective to minimize)

Constraint categories (P1-P3 properties):
1. Transmission–reconfiguration precedence
2. No overlapping activities on same OCS
3. Cross-step synchronization

### Batch Experiment System

**Matrix experiments** enable systematic parameter sweeps:

1. **Matrix specification** (`config/matrix/paper/*.toml` and `config/matrix/examples/*.toml`): Defines parameter grids
   - `matrix_id`: Unique experiment identifier
   - `topology`: Network parameters (k, p, B, T_reconf, T_lat)
   - `message_sizes_mib`: List of message sizes to sweep
   - `algorithms`: List of collective algorithms
   - `output`: Config directory and results CSV path

2. **scripts/generate_matrix_configs.py**: Generates individual instance.toml files for each parameter combination, creates `index.json` with config hashes for resumability

3. **scripts/matrix_runner.py**: Orchestrates batch execution
   - Creates isolated run directories: `logs/runs/<timestamp>_<config_name>/`
   - Each run directory contains: `config/`, `figures/`, `solution/`, `run.log`, `metrics.json`, `metadata.json`
   - Appends results to `logs/matrix_results.csv` with fields: timestamp, matrix_id, algorithm, message_size, network params, solve time, CCT values, improvement percentages
   - Supports resume (`--resume`), failure retry (`--rerun-failed`), partial execution (`--limit`), periodic heartbeats (`--heartbeat-sec`), and JSON progress snapshots (`--progress-file`)

4. **scripts/matrix_archive.py**: Archive completed matrix experiments to `logs/archive/`

### Output Structure

- **figures/**: Gantt chart PDFs showing OCS reconfiguration and transmission timelines
- **solution/**: Solution files (JSON or .sol format)
- **logs/runs/<run-id>/**: Per-run isolated artifacts (for matrix experiments)
- **logs/matrix_results.csv**: Aggregated experiment results for analysis

### Utilities

**utils/scheduler_analysis.py**:
- `extract_results()`: Parse solved model and extract schedule
- `plot_schedule()`: Generate Gantt chart visualization

**utils/check_platform.py**: Platform detection (used for ARM Mac CBC solver path)

## Common Development Tasks

### Adding a New Collective Algorithm

1. Add computation function in `config/cc_algorithm.py`:
   ```python
   def compute_my_algorithm_params(p: int, m: float) -> Dict[str, object]:
       return {
           'p': p_adjusted,
           'num_steps': ...,
           'm_i': {...},  # Dict[int, float]
           'configurations': {...},  # Dict[int, int]
       }
   ```

2. Register in `compute_algorithm_params()`:
   ```python
   if algorithm == 'my_algorithm':
       return compute_my_algorithm_params(p, m)
   ```

3. Update `config/instance.toml` algorithm options comment

### Modifying the MILP Model

Both `paradigm/model_gurobi.py` and `paradigm/model_pulp.py` must be updated in parallel:

1. Add decision variables in both files
2. Add constraints following the same structure
3. Update `extract_results()` in `utils/scheduler_analysis.py` if new variables need visualization
4. If modifying warm start, update `paradigm/warm_start.py`

### Running Notebook Analysis

```bash
# Install notebook dependencies
uv sync --extra notebook

# In VS Code: Select Python interpreter from .venv
# Open .ipynb file and select .venv kernel
```

If kernel not recognized:
```bash
uv run python -m ipykernel install --user \
  --name overlap4ocs \
  --display-name "overlap4ocs (.venv)"
```

## Solver Notes

### Gurobi
- Requires valid license
- Best performance for large-scale instances
- Supports warm start and detailed diagnostics
- Time limits may not fully halt optimization (incumbent solution returned if available)

### PuLP (open-source)
- Uses CBC solver by default
- ARM Mac requires Homebrew CBC: `/opt/homebrew/opt/cbc/bin/cbc`
- Can use Gurobi backend via `solver = "pulp_gurobi"` (requires Gurobi CLI, not Python API)
- Slower than native Gurobi but sufficient for small/medium instances

### COPT
- Alternative commercial solver
- Integrated via PuLP interface
- `solver_gap` and `solver_time_limit` not currently implemented

## Key Constraints and Patterns

### Configuration Changes
When adding topology configurations, note that:
- Configuration indices in `configurations` dict determine when OCS reconfiguration is required
- If `configurations[i] != configurations[i-1]`, reconfiguration is triggered
- The model automatically handles this through binary variable `r[i,j]`

### Warm Start
The system attempts warm start in this priority:
1. One-shot solution (if feasible and better than baseline)
2. Baseline solution
3. No warm start if neither is available

After optimization, if the final solution is worse than the warm start (can happen with time limits), the system automatically falls back to the warm start schedule.

### Debug Mode
- `debug_mode = 1`: Runs a relaxed "debug model" and validates both debug and production solutions
- `debug_mode = 2`: Loads and validates a manually specified solution file

## Important File Locations

- Mathematical formulation: `docs/math_model.md`
- Parameter validation: `config/instance_parser.py`
- Main solver interface: `paradigm/solver_wrapper.py`
- Baseline/ideal/one-shot paradigms: `paradigm/baseline.py`, `paradigm/ideal.py`, `paradigm/one_shot.py`
- Result extraction and plotting: `utils/scheduler_analysis.py`
