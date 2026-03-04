# Matrix Experiment Infrastructure

This document explains how the matrix experiment toolchain works and how to
extend it for new scenarios.

## Goals

- **Parameter coverage**: declare large combinations of topology, algorithm, and message size once, then run them automatically.
- **Deterministic reproduction**: regenerate the same `instance.toml` files and rerun selected subsets without manual editing.
- **Full traceability**: store each run under `logs/runs/<run-id>/` with configs, logs, metrics, figures, and solutions.
- **Unified analysis**: append each run to the matrix `results_csv`, then aggregate for paper plots using `scripts/prepare_simulation_data.py`.

## Matrix Spec Locations

- `config/matrix/paper/`: specs used by the paper reproducibility workflow.
- `config/matrix/examples/`: extra templates and historical sweeps.

Each matrix spec is a TOML file. Example reference:
`config/matrix/examples/example_matrix_sweep_msg+k.toml`.

## Matrix Spec Schema

| Field | Required | Description |
| --- | --- | --- |
| `matrix_id` | Yes | Unique identifier used in generated config names and CSV rows. |
| `solver` | No | Shared solver for all instances (default: `pulp`). |
| `program_config` | No | Runtime `program.toml` snapshot path. |
| `message_sizes_mib` | Yes | Message sizes in MiB. |
| `algorithms` | Yes | Algorithm list such as `ar_having-doubling`, `a2a_pairwise`, `a2a_bruck`. |
| `[topology]` | Yes | Topology fields such as `k`, `p`, `B`, `T_reconf`, `T_lat`. |
| `[output]` | No | Output controls: `config_dir`, `results_csv`, `runs_root`. |

Multiple specs can coexist as long as `matrix_id` values are distinct.

## Stage 1: Generate Instance Configs

Example:

```bash
PYTHONPATH=. python scripts/generate_matrix_configs.py \
  --matrix config/matrix/examples/example_matrix_sweep_msg+k.toml
```

What happens:

1. Parse and validate required fields in the matrix spec.
2. Write all instance combinations into `logs/generated_configs/<matrix_id>/`.
3. Write `index.json` with config path, algorithm, message size, solver, and config hash.
4. Without `--overwrite`, existing files raise an error to prevent accidental replacement.

Use `--overwrite` when you intentionally regenerate after spec updates.

## Stage 2: Run Matrix Experiments

Example:

```bash
PYTHONPATH=. python scripts/matrix_runner.py \
  --matrix config/matrix/examples/example_matrix_sweep_msg+k.toml
```

Key behaviors:

1. Ensure generated configs exist (`--regenerate` forces regeneration).
2. Use entry hashes in `results_csv` to skip completed runs by default.
3. Execute each pending config through `main.py` and collect run artifacts.
4. Append one CSV row per run with status, timing, CCT metrics, improvement, and hash.
5. Support recovery and control options:
   - `--limit N`
   - `--no-resume`
   - `--rerun-failed`
   - `--extra-args "..."` (forwarded to `main.py`)
   - `--dry-run`

## Run Artifacts

Per-run layout:

```text
logs/runs/<run-id>/
  |- config/        # instance + program snapshots
  |- figures/       # solution/baseline/oneshot PDFs
  |- solution/      # JSON solution files
  |- logs/run.log   # main + solver output
  |- metrics.json   # metrics written by main.py
  |- metadata.json  # command, git info, duration, artifacts
```

The matrix `results_csv` path comes from each spec's `[output]` section.

## Recommended Workflow

1. Create or edit a matrix spec under `config/matrix/paper/` or `config/matrix/examples/`.
2. Generate configs:
   ```bash
   PYTHONPATH=. python scripts/generate_matrix_configs.py \
     --matrix config/matrix/examples/<your_spec>.toml --overwrite
   ```
3. Run full or partial sweep:
   ```bash
   PYTHONPATH=. python scripts/matrix_runner.py \
     --matrix config/matrix/examples/<your_spec>.toml --limit 10
   ```
4. Inspect `results_csv`, `logs/runs/<run-id>/metrics.json`, or plotting tools (`scripts/simulation_fig.ipynb` / `scripts/simulation_fig.py`).
5. For paper-level plotting inputs, run:
   ```bash
   PYTHONPATH=. python scripts/prepare_simulation_data.py --target all
   ```
