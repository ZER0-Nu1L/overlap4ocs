# Repository Guidelines

## Project Structure & Module Organization
Core execution starts in `main.py` and orchestration logic lives in `orchestrator.py`. Keep domain logic split by purpose:
- `config/`: instance/program TOML parsing and collective algorithm definitions (`cc_algorithm.py`), plus matrix specs in `config/matrix/paper/` and `config/matrix/examples/`.
- `paradigm/`: scheduling baselines, warm start logic, and MILP solvers (`model_gurobi.py`, `model_pulp.py`, `solver_wrapper.py`).
- `utils/`: result extraction and plotting helpers.
- `scripts/`: batch experiment tooling (`generate_matrix_configs.py`, `matrix_runner.py`, `matrix_archive.py`).
- `notebook/`: analysis notebooks.
Generated artifacts go to `figures/`, `solution/`, `logs/`, and `archives/` (all ignored by git).

## Build, Test, and Development Commands
Use Python 3.10+ and `uv` by default.
- `uv sync`: install runtime dependencies.
- `uv sync --extra gurobi`: add Gurobi support.
- `uv sync --extra notebook`: add Jupyter tooling.
- `uv run python main.py --config config/instance.toml`: run one optimization instance.
- `PYTHONPATH=. uv run python scripts/generate_matrix_configs.py --matrix config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml`: generate sweep configs.
- `PYTHONPATH=. uv run python scripts/matrix_runner.py --matrix config/matrix/paper/exp2.2-matrix_sweep_msg+Tr.toml --limit 1 --resume --heartbeat-sec 10`: quick batch smoke run.
- `PYTHONPATH=. uv run python scripts/matrix_runner.py --matrix <matrix.toml> --resume --rerun-failed --heartbeat-sec 30`: long-run default with resumability and heartbeat.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for modules/functions/variables, concise docstrings for public functions. Keep parameter names consistent with config keys (`k`, `p`, `m`, `T_reconf`, etc.). When changing optimization constraints, keep `model_gurobi.py` and `model_pulp.py` behavior aligned.

## Testing Guidelines
There is no dedicated `tests/` suite yet. Use reproducible smoke checks:
1. Run a single instance via `main.py`.
2. Run a limited matrix job (`--limit 1`) to validate script orchestration.
3. Confirm new outputs under `logs/runs/...` and expected PDFs/JSON artifacts.
4. For long matrix runs, check live progress via `logs/repro/<matrix_id>_progress.json`.
Include exact command lines used in PR descriptions.

## Commit & Pull Request Guidelines
Recent history uses bracketed commit prefixes such as `[feat]`, `[fix]`, `[refactor]`, `[docs]`, `[chore]`, `[improve]`. Keep commits focused and imperative (example: `[fix] enforce warm-start fallback guard`).
For PRs, include:
- purpose and impacted modules,
- config(s)/solver used for verification,
- key result deltas (for example CCT improvement),
- linked issue (if applicable),
- relevant artifact paths (for example `logs/runs/<id>/metrics.json`).

## Security & Configuration Tips
Never commit solver licenses, credentials, or machine-local paths. Prefer editing TOML in `config/` instead of hardcoding runtime constants.
