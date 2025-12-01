#!/usr/bin/env python3
"""Coordinate large matrix experiments and aggregate their results."""
from __future__ import annotations

import argparse
import csv
import json
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

# Ensure project root is importable when invoked via python scripts/matrix_runner.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_matrix_configs import load_matrix_spec, write_configs  # type: ignore
from config.instance_parser import get_parameters  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an experiment matrix and log outcomes")
    parser.add_argument('--matrix', required=True, help='Matrix spec toml path')
    parser.add_argument('--regenerate', action='store_true', help='Force regeneration of config files/index')
    parser.add_argument('--resume', dest='resume', action='store_true', default=True, help='Skip configs already logged in results CSV (default)')
    parser.add_argument('--no-resume', dest='resume', action='store_false', help='Ignore previous CSV entries')
    parser.add_argument('--rerun-failed', action='store_true', help='Rerun entries that previously recorded non-success status')
    parser.add_argument('--limit', type=int, help='Optional cap on number of configs to execute this pass')
    parser.add_argument('--extra-args', default='', help='Extra CLI args forwarded to main.py (quoted string)')
    parser.add_argument('--python-bin', default=sys.executable, help='Python interpreter for main.py')
    parser.add_argument('--main-script', default='main.py', help='Entry script invoked per experiment')
    parser.add_argument('--program-config', default=None, help='program.toml override (falls back to matrix spec)')
    parser.add_argument('--output-root', default=None, help='Per-run artifact root override (falls back to matrix spec)')
    parser.add_argument('--results-csv', default=None, help='Results CSV override (falls back to matrix spec)')
    parser.add_argument('--dry-run', action='store_true', help='Create run folders without executing main.py')
    parser.add_argument('--skip-artifact-copy', action='store_true', help='Do not copy figures/solutions into run folders')
    return parser.parse_args()


def ensure_configs(spec: dict, regenerate: bool) -> List[dict]:
    output_cfg = spec.get('output', {})
    cfg_dir = Path(output_cfg.get('config_dir', 'logs/generated_configs'))
    index_path = cfg_dir / 'index.json'

    if regenerate or not index_path.exists():
        overwrite = regenerate
        entries = write_configs(spec, cfg_dir, overwrite=overwrite)
    else:
        with index_path.open() as f:
            entries = json.load(f)
    return entries


def load_existing_hashes(csv_path: Path) -> Dict[str, str]:
    if not csv_path.exists():
        return {}
    hashes: Dict[str, str] = {}
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            h = row.get('hash')
            if not h:
                continue
            hashes[h] = row.get('status', '')
    return hashes


def append_row(csv_path: Path, header: Sequence[str], row: Dict[str, object]) -> None:
    csv_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('a', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        if not csv_exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, '') for key in header})


def load_metrics(metrics_path: Path) -> dict | None:
    if not metrics_path.exists():
        return None
    with metrics_path.open() as fh:
        return json.load(fh)


def build_run_id(config_path: Path) -> str:
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return f"{timestamp}_{config_path.stem}"


def capture_cmd(args: List[str]) -> str:
    try:
        result = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except Exception:
        return ""


def expected_artifacts(params: dict) -> dict:
    return {
        'solution_figure': f"figures/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.pdf",
        'solution_file': f"solution/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.json",
        'baseline_figure': f"figures/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.pdf",
        'baseline_file': f"solution/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json",
        'oneshot_figure': f"figures/oneshot_{params['algorithm']}_t_k={params['k']}_p={params['p']}_m={params['m']}.pdf",
        'oneshot_file': f"solution/oneshot_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json"
    }


def copy_artifacts(artifact_map: dict, destination: Path) -> List[str]:
    copied: List[str] = []
    fig_dir = destination / 'figures'
    sol_dir = destination / 'solution'
    log_dir = destination / 'logs'
    fig_dir.mkdir(exist_ok=True)
    sol_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    for key, rel_path in artifact_map.items():
        src = Path(rel_path)
        if not src.exists():
            continue
        if src.parent.name == 'figures':
            target = fig_dir
        elif src.parent.name == 'solution':
            target = sol_dir
        else:
            target = destination
        shutil.copy2(src, target / src.name)
        copied.append(key)

    gurobi_log = Path('logs/gurobi.log')
    if gurobi_log.exists():
        shutil.copy2(gurobi_log, log_dir / 'gurobi.log')
        copied.append('gurobi_log')
    return copied


def snapshot_configs(instance_config: Path, program_config: Path, destination: Path) -> None:
    cfg_dir = destination / 'config'
    cfg_dir.mkdir(exist_ok=True)
    shutil.copy2(instance_config, cfg_dir / instance_config.name)
    if program_config.exists():
        shutil.copy2(program_config, cfg_dir / program_config.name)


def run_experiment(opts: argparse.Namespace, config_path: Path, extra_main_args: List[str]) -> dict:
    run_id = build_run_id(config_path)
    output_root = Path(opts.output_root).resolve()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    program_config = Path(opts.program_config)
    snapshot_configs(config_path, program_config, run_dir)

    git_commit = capture_cmd(['git', 'rev-parse', 'HEAD'])
    git_status = capture_cmd(['git', 'status', '-sb'])

    params = get_parameters(str(config_path))
    artifacts = expected_artifacts(params)

    param_subset = {key: params.get(key) for key in ('k', 'T_reconf', 'T_lat', 'B', 'p', 'm', 'solver_gap', 'solver_time_limit')}

    metadata = {
        'run_id': run_id,
        'config': str(config_path),
        'program_config': str(program_config),
        'timestamp': datetime.now().isoformat(),
        'git_commit': git_commit,
        'git_status': git_status,
        'command': {
            'python': opts.python_bin,
            'script': opts.main_script,
            'extra_args': extra_main_args,
        },
        'artifacts': artifacts,
        'parameters': param_subset,
    }

    metrics_path = run_dir / 'metrics.json'
    log_path = run_dir / 'run.log'
    cmd = [opts.python_bin, opts.main_script, '--config', str(config_path), '--metrics-file', str(metrics_path), '--run-id', run_id]
    cmd.extend(extra_main_args)

    if opts.dry_run:
        metadata['status'] = 'skipped'
        metadata['returncode'] = None
        metadata['duration_seconds'] = 0
        metadata['copied_artifacts'] = []
    else:
        start = time.time()
        with open(log_path, 'w') as log_file:
            result = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        duration = time.time() - start
        metadata['returncode'] = result.returncode
        metadata['duration_seconds'] = duration
        metadata['status'] = 'success' if result.returncode == 0 else 'failed'
        if result.returncode == 0 and not opts.skip_artifact_copy:
            metadata['copied_artifacts'] = copy_artifacts(artifacts, run_dir)
        else:
            metadata['copied_artifacts'] = []

    with open(run_dir / 'metadata.json', 'w') as meta_file:
        json.dump(metadata, meta_file, indent=2)

    return metadata


def main():
    args = parse_args()
    spec = load_matrix_spec(Path(args.matrix))
    entries = ensure_configs(spec, regenerate=args.regenerate)

    output_cfg = spec.get('output', {})
    runs_root = Path(args.output_root or output_cfg.get('runs_root', 'logs/runs'))
    results_csv = Path(args.results_csv or output_cfg.get('results_csv', 'logs/matrix_results.csv'))
    program_config = args.program_config or spec.get('program_config', 'config/program.toml')

    completed = load_existing_hashes(results_csv) if args.resume else {}
    extra_main_args = shlex.split(args.extra_args.strip()) if args.extra_args else []

    batch_args = argparse.Namespace(
        output_root=str(runs_root),
        program_config=program_config,
        python_bin=args.python_bin,
        main_script=args.main_script,
        dry_run=args.dry_run,
        skip_artifact_copy=args.skip_artifact_copy,
    )

    header = [
        'timestamp', 'matrix_id', 'run_id', 'config_path', 'algorithm', 'message_mib', 'solver',
        'solver_gap', 'solver_time_limit',
        'k', 'T_reconf', 'T_lat', 'B', 'p',
        'status', 'returncode', 'duration_seconds', 'optimized_cct', 'baseline_cct', 'oneshot_cct',
        'ideal_cct', 'improvement_over_baseline_pct', 'metrics_path', 'hash'
    ]

    executed = 0
    pending_entries = []
    for entry in entries:
        entry_hash = entry.get('hash')
        if args.resume and entry_hash in completed:
            prior_status = completed[entry_hash]
            if not (args.rerun_failed and prior_status != 'success'):
                continue
        pending_entries.append(entry)

    total = len(pending_entries)
    if args.limit is not None:
        pending_entries = pending_entries[:args.limit]

    print(f"Planned runs: {len(pending_entries)} (from {total} pending entries)")

    for entry in pending_entries:
        metadata = run_experiment(batch_args, Path(entry['config']), extra_main_args)
        run_dir = runs_root / metadata['run_id']
        metrics_path = run_dir / 'metrics.json'
        metrics = load_metrics(metrics_path)
        cct = metrics.get('cct') if metrics else {}
        improvement = metrics.get('improvement_percent', {}).get('over_baseline') if metrics else None

        params = metadata.get('parameters', {}) or {}

        row = {
            'timestamp': metadata.get('timestamp'),
            'matrix_id': spec['matrix_id'],
            'run_id': metadata.get('run_id'),
            'config_path': entry.get('config'),
            'algorithm': entry.get('algorithm'),
            'message_mib': entry.get('message_mib'),
            'solver': entry.get('solver'),
            'solver_gap': params.get('solver_gap'),
            'solver_time_limit': params.get('solver_time_limit'),
            'k': params.get('k'),
            'T_reconf': params.get('T_reconf'),
            'T_lat': params.get('T_lat'),
            'B': params.get('B'),
            'p': params.get('p'),
            'status': metadata.get('status'),
            'returncode': metadata.get('returncode'),
            'duration_seconds': metadata.get('duration_seconds'),
            'optimized_cct': (cct or {}).get('optimized'),
            'baseline_cct': (cct or {}).get('baseline'),
            'oneshot_cct': (cct or {}).get('oneshot'),
            'ideal_cct': (cct or {}).get('ideal'),
            'improvement_over_baseline_pct': improvement,
            'metrics_path': str(metrics_path) if metrics_path.exists() else '',
            'hash': entry.get('hash'),
        }
        append_row(results_csv, header, row)
        executed += 1
        print(f"[RUN {executed}/{len(pending_entries)}] {entry['config']} -> status={metadata['status']}")

    print(f"Matrix sweep complete. Executed {executed} runs. Results appended to {results_csv}")


if __name__ == '__main__':
    main()
