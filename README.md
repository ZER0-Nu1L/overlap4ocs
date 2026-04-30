# SWOT: Enabling Reconfiguration-Communication Overlap for Collective Communication in Optical Networks

[![Paper](https://img.shields.io/badge/arXiv-2510.19322-b31b1b.svg)](https://arxiv.org/abs/2510.19322)
[![DOI](https://zenodo.org/badge/861492578.svg)](https://doi.org/10.5281/zenodo.19924120)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> **Official implementation** of ["Enabling Reconfiguration-Communication Overlap for Collective Communication in Optical Networks"](https://arxiv.org/abs/2510.19322), accepted at ACM CoNEXT 2026.

[English](README.md) | [中文](README_ZH.md)

## 📖 Overview

SWOT (Scheduler for Workload-aligned Optical/Overlapping Topologies) is a framework that **overlaps optical circuit switch (OCS) reconfigurations with data transmissions** to minimize communication completion time (CCT) in distributed machine learning systems. Unlike traditional static pre-configured approaches, SWOT dynamically aligns network resources with collective communication traffic patterns through intra-collective reconfiguration.

### Key Features

- **🚀 25.0%-74.1% CCT Reduction**: Significant performance improvements over static baseline approaches
- **⚡ Reconfiguration-Communication Overlap**: Hides up to 53% reconfiguration overhead by overlapping with data transmission
- **🎯 MILP-Based Optimization**: Formulates joint scheduling as Mixed Integer Linear Programming for optimal solutions
- **🔧 Multi-Solver Support**: Works with commercial (Gurobi) and open-source (PuLP/COPT) solvers
- **📊 Comprehensive Evaluation**: Supports multiple collective algorithms for each primitive (AllReduce, AllToAll, AllGather, ReduceScatter)
- **🔬 Reproducible Research**: Complete experimental framework with automated parameter sweeps

### Supported Collective Algorithms

| Primitive | Algorithms |
|-----------|-----------|
| **AllReduce** | Ring, Halving-Doubling (Rabenseifner), Recursive-Doubling |
| **AllToAll** | Pairwise Exchange, Bruck's Algorithm |
| **AllGather** | Halving-Doubling |
| **ReduceScatter** | Halving-Doubling |

> SWOT supports most of the algorithms for each Collective Primitive, but in this codebase, we mainly implemented the typical algorithms mentioned above. If you need to extend it, you can add your own implementations in config/cc_algorithm.py.
>
> Note: for paper plotting in `scripts/simulation_fig.ipynb` / `scripts/simulation_fig.py`, we also include analytical AllReduce baselines such as `ar_dbt` and `ar_dbt_pipe`. These are comparison models computed in scripts, not scheduling algorithms registered in `config/cc_algorithm.py`.

## 🏗️ Architecture

```mermaid
flowchart TB
  subgraph SWOT_Scheduler["SWOT Scheduler"]
    direction TB
    subgraph Options["Scheduling Options"]
      direction LR
      Baseline["Baseline<br/>Schedule"]
      OneShot["One-Shot<br/>Schedule"]
      MILP["MILP Optimizer<br/>(Gurobi / PuLP)"]
    end
    Joint["Joint Reconfiguration-<br/>Transmission Scheduling"]
    Gantt["Gantt Chart Visualization<br/>+ Solution Validation"]
  end

  Baseline --> Joint
  OneShot  --> Joint
  MILP     -->|warm start input| Joint
  Joint     --> Gantt
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js/npm (optional, for development)
- Gurobi license (optional, for commercial solver)

### Installation

We recommend using [uv](https://github.com/astral-sh/uv) for dependency management:

```bash
# Install uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via Homebrew
brew install uv

# Clone the repository
git clone https://github.com/ZER0-Nu1L/overlap4ocs.git
cd overlap4ocs

# Install dependencies
uv sync

# Optional: Install with Gurobi support
uv sync --extra gurobi

# Optional: Install with Jupyter notebook support
uv sync --extra notebook
```

> This repository standardizes on `uv`; a parallel `pip` workflow is intentionally not maintained.

### Running a Single Experiment

```bash
# Run with default configuration
uv run python main.py --config config/instance.toml

# Run with custom solver settings
uv run python main.py \
  --config config/instance.toml \
  --metrics-file logs/demo_metrics.json \
  --run-id demo-run

# Export fixed PNG schedules with custom figure size
uv run python main.py \
  --config config/instance.toml \
  --program-config config/program_png.toml
```

**Expected Output:**
- Gantt chart visualization: `figures/solution_*.pdf`
- Fixed-name PNG charts (when using `config/program_png.toml`):
  - `figures/optimized_schedule.png`
  - `figures/baseline_schedule.png`
- Solution file: `solution/solution_*.json`
- Performance metrics in console

### Example Output

```
PuLP solver is available
Parameters loaded from config/instance.toml
...
Comparison:
One-shot CCT: None
One-shot schedule is not feasible for current parameters
Baseline CCT:  1480 μs
Optimized CCT: 1140 μs
Improvement over baseline: 23%
```

## 📊 Running Batch Experiments

For systematic parameter sweeps and reproducible research:

### 1. Generate Configuration Matrix

```bash
PYTHONPATH=. uv run python scripts/generate_matrix_configs.py \
  --matrix config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml
```

This creates individual configuration files in `logs/generated_configs/<matrix_id>/`.

### 2. Execute Experiment Matrix

```bash
PYTHONPATH=. uv run python scripts/matrix_runner.py \
  --matrix config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml
```

**Options:**
- `--limit N`: Run only N configurations
- `--rerun-failed`: Re-execute failed runs
- `--resume`: Skip already completed runs (default)
- `--extra-args "..."`: Pass additional arguments to main.py

**Output Structure:**
```
logs/runs/<timestamp>_<config_name>/
├── config/
│   ├── instance.toml
│   └── program.toml
├── figures/
│   ├── baseline_*.pdf
│   ├── oneshot_*.pdf
│   └── solution_*.pdf
├── solution/
│   ├── baseline_*.json
│   ├── oneshot_*.json
│   └── solution_*.json
├── metrics.json
├── metadata.json
└── run.log
```

### 3. Archive Experiments

```bash
uv run python scripts/matrix_archive.py \
  --matrix-id exp2.2-matrix_sweep_msg+Tr \
  --cleanup
```

## ⚙️ Configuration

### Instance Configuration (`config/instance.toml`)

```toml
# Solver configuration
solver = "pulp"              # Options: "gurobi", "pulp", "copt"
solver_gap = 0.05            # Relative MIP gap tolerance (5%)
solver_time_limit = 120      # Time limit in seconds

# Network topology
k = 2                        # Number of OCS switches
p = 8                        # Number of compute nodes
B = 50                       # Bandwidth per link (GBps)
T_reconf = 0.2               # OCS reconfiguration time (ms)
T_lat = 0.02                 # End-to-end base latency (ms)

# Workload
m = 32                       # Message size (MB)
algorithm = "ar_having-doubling"  # Collective algorithm
```

### Program Configuration (`config/program.toml`)

```toml
save_as_pdf = true           # Save Gantt charts as PDF
debug_mode = 0               # 0: off, 1: debug model, 2: comparison
show = false                 # Display charts interactively
```

### PNG Export Configuration (`config/program_png.toml`)

```toml
save_as_pdf = true
show = false
debug_mode = 0

figure_format = "png"
figure_width = 16
figure_height = 4
figure_dpi = 160

optimized_figure_filename = "figures/optimized_schedule.png"
baseline_figure_filename = "figures/baseline_schedule.png"
```

### Supported Algorithms

| Algorithm ID | Description |
|--------------|-------------|
| `ar_ring` | AllReduce with Ring algorithm |
| `ar_having-doubling` | AllReduce with Rabenseifner's algorithm |
| `ar_recursive-doubling` | AllReduce with Recursive-Doubling |
| `a2a_pairwise` | AllToAll with Pairwise Exchange |
| `a2a_bruck` | AllToAll with Bruck's algorithm |
| `ag_having-doubling` | AllGather with Halving-Doubling |
| `rs_having-doubling` | ReduceScatter with Halving-Doubling |

## 📐 Mathematical Formulation

The SWOT scheduler formulates the joint optimization problem as a Mixed Integer Linear Program (MILP):

**Objective:** Minimize Communication Completion Time (CCT)

**Decision Variables:**
- `d[i,j]`: Data volume assigned to OCS j at step i
- `u[i,j]`: Binary indicator if OCS j is used at step i
- `r[i,j]`: Binary indicator if OCS j is reconfigured at step i
- `t_start[i,j]`, `t_end[i,j]`: Transmission start/end times
- `t_reconf_start[i,j]`, `t_reconf_end[i,j]`: Reconfiguration start/end times

**Key Constraints:**
1. **P1 (Transmission-Reconfiguration Precedence)**: Data transmission starts only after reconfiguration completes
2. **P2 (No Overlapping Activities)**: An OCS cannot perform two activities simultaneously
3. **P3 (Cross-Step Synchronization)**: Each step begins only after the previous step finishes

See [`docs/math_model.md`](docs/math_model.md) for detailed mathematical formulation.

## 📁 Repository Structure

```
overlap4ocs/
├── .github/
│   └── workflows/               # CI smoke / repro-lite / repro-full
├── main.py                      # Main entry point
├── config/
│   ├── instance.toml           # Problem instance parameters
│   ├── program.toml            # Runtime configuration
│   ├── program_png.toml        # Fixed-name PNG export configuration
│   ├── instance_parser.py      # Configuration parser
│   ├── cc_algorithm.py         # Collective algorithm definitions
│   └── matrix/
│       ├── paper/              # Matrix specs used by paper reproduction
│       └── examples/           # Extra sweep templates and historical examples
├── paradigm/
│   ├── model_gurobi.py         # Gurobi MILP formulation
│   ├── model_pulp.py           # PuLP MILP formulation
│   ├── solver_wrapper.py       # Unified solver interface
│   ├── baseline.py             # Baseline scheduling
│   ├── one_shot.py             # One-shot pre-configuration
│   ├── ideal.py                # Theoretical lower bound
│   └── warm_start.py           # Warm start initialization
├── scripts/
│   ├── generate_matrix_configs.py  # Generate experiment configs
│   ├── matrix_runner.py            # Execute batch experiments
│   ├── matrix_archive.py           # Archive experiment results
│   ├── prepare_simulation_data.py  # Build merged CSVs used by paper plotting
│   ├── simulation_fig.py           # Reproducible CLI figure generation (exp1.x/exp2.x)
│   └── simulation_fig.ipynb        # Full paper plotting notebook
├── utils/
│   ├── scheduler_analysis.py   # Result extraction & visualization
│   └── check_platform.py       # Platform detection
├── docs/
│   ├── math_model.md           # Mathematical formulation
│   ├── exp1.3-a2a-time-limit-study.md  # Solver time-limit study notes
│   └── reproducibility.md      # Reproducibility workflow
├── CLAUDE.md                   # Development guide
└── README.md                   # This file
```

## 🔬 Reproducing Paper Results

The paper figure pipeline depends on `scripts/simulation_fig.ipynb` plus matrix CSV outputs.
For direct reproducibility, use the scripted workflow below:

```bash
# 1) Run matrix experiments
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
  PYTHONPATH=. uv run python scripts/matrix_runner.py --matrix "$matrix"
done

# 2) Build merged CSVs referenced by the notebook
uv run python scripts/prepare_simulation_data.py --target all

# Note: exp1.3 merged CSVs intentionally reuse compatible exp1.1 baselines:
# - exp1.3_ar: exp1.3 recursive-doubling + exp1.1 halving-doubling + analytical AR baselines
# - exp1.3_a2a_256: exp1.3 pairwise + exp1.1 bruck
# (all reused rows are filtered by matching topology/runtime)
# This reduces duplicate compute while preserving consistent comparison baselines.

# 3a) Reproducible CLI plotting (exp1.1/1.2/1.3 + exp2.1/2.2)
uv run python scripts/simulation_fig.py --write-summary --output-dir figures/paper

# Note: this overwrites files with the same names under figures/paper.
# If you keep manually uploaded paper figures there, use another directory:
# uv run python scripts/simulation_fig.py --write-summary --output-dir figures/paper_reproduce

# 3b) Interactive notebook plotting (full paper plots)
uv sync --extra notebook
jupyter notebook scripts/simulation_fig.ipynb
```

For full mapping from matrix configs to generated CSV files and figure entry points, see
[`docs/reproducibility.md`](docs/reproducibility.md).

## 📊 Visualization

SWOT generates Gantt charts showing:
- OCS reconfiguration periods (red bars)
- Data transmission periods (blue bars)
- Timeline for each OCS switch
- Step boundaries and synchronization points

Example output visualizations (from `config/instance.toml` + `config/program_png.toml`):

![Baseline Schedule Visualization](figures/baseline_schedule.png)
*(Baseline schedule for the same instance)*

![Optimized Schedule Visualization](figures/optimized_schedule.png)
*(Optimized reconfiguration-transmission overlap schedule)*


## 🛠️ Development

### Adding a New Collective Algorithm

1. Define algorithm parameters in `config/cc_algorithm.py`:

```python
def compute_my_algorithm_params(p: int, m: float) -> Dict[str, object]:
    return {
        'p': p_adjusted,
        'num_steps': num_steps,
        'm_i': {1: m/2, 2: m/2, ...},  # Message sizes per step
        'configurations': {1: 1, 2: 2, ...},  # OCS configs per step
    }
```

2. Register in `compute_algorithm_params()`:

```python
if algorithm == 'my_algorithm':
    return compute_my_algorithm_params(p, m)
```

### Running Tests

```bash
# Run a small test instance
uv run python main.py --config config/instance.toml

# Validate solution
uv run python -c "
from paradigm.solver_wrapper import load_and_validate_solution
from config.instance_parser import get_parameters
params = get_parameters('config/instance.toml')
load_and_validate_solution(
    params,
    'solution/solution_ar_having-doubling_break_k=2_p=8_m=32.json',
    solver=params['solver']
)
"
```

## 📝 Citation

If you mention SWOT in your research, please cite our paper:

The ACM DOI is listed for the camera-ready PACMNET/CoNEXT record. If DOI resolution is not active yet, use the arXiv URL as the current public paper link.

```bibtex
@article{wuSWOTEnablingCommunicationReconfiguration2026,
  title = {{SWOT}: Enabling Communication-Reconfiguration Overlap for Collective Communication in Optical Networks},
  author = {Wu, Changbo and Yu, Zhuolong and Zhao, Gongming and Xu, Hongli},
  journal = {Proceedings of the ACM on Networking},
  volume = {4},
  number = {CoNEXT2},
  articleno = {24},
  year = {2026},
  month = jun,
  doi = {10.1145/3808672},
  url = {https://arxiv.org/abs/2510.19322}
}
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- MILP solvers: [Gurobi Optimization](https://www.gurobi.com/), [COIN-OR PuLP](https://github.com/coin-or/pulp)

## 📧 Contact

For questions, issues, or collaboration inquiries:
- Open an issue on [GitHub Issues](https://github.com/ZER0-Nu1L/overlap4ocs/issues)
- Contact: [Email](wuchangbo@mail.ustc.edu.cn)

---

**Note:** This is a research prototype.
