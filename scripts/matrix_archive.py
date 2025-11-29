#!/usr/bin/env python3
"""Archive or clean matrix experiment artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

HEADER = [
    'timestamp', 'matrix_id', 'run_id', 'config_path', 'algorithm', 'message_mib', 'solver',
    'status', 'returncode', 'duration_seconds', 'optimized_cct', 'baseline_cct', 'oneshot_cct',
    'ideal_cct', 'improvement_over_baseline_pct', 'metrics_path', 'hash'
]


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def write_rows(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for val in values:
        if not val or val in seen:
            continue
        seen.add(val)
        result.append(val)
    return result


def archive_data(matrix_id: str, rows: List[Dict[str, str]], runs_root: Path, archive_root: Path,
                 config_prefix: Path | None, matrix_spec: Path | None, copy_runs: bool, copy_configs: bool) -> Path:
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = archive_root / matrix_id / timestamp
    dest.mkdir(parents=True, exist_ok=True)

    # write filtered csv
    subset_csv = dest / 'results.csv'
    write_rows(subset_csv, [row for row in rows if row['matrix_id'] == matrix_id])

    if matrix_spec and matrix_spec.exists():
        shutil.copy2(matrix_spec, dest / Path(matrix_spec).name)

    if copy_runs:
        runs_dest = dest / 'runs'
        runs_dest.mkdir(exist_ok=True)
        for run_id in unique(row['run_id'] for row in rows if row['matrix_id'] == matrix_id):
            if not run_id:
                continue
            src = runs_root / run_id
            if src.exists():
                shutil.copytree(src, runs_dest / run_id)

    if copy_configs and config_prefix:
        cfg_dest = dest / 'configs'
        cfg_dest.mkdir(exist_ok=True)
        for cfg in unique(row['config_path'] for row in rows if row['matrix_id'] == matrix_id):
            if not cfg:
                continue
            src = Path(cfg)
            if not src.exists():
                continue
            if not safe_relative(src, config_prefix):
                continue
            shutil.copy2(src, cfg_dest / src.name)

    return dest


def cleanup_data(matrix_id: str, rows: List[Dict[str, str]], runs_root: Path, config_prefix: Path | None,
                  results_csv: Path) -> None:
    keep_rows = [row for row in rows if row['matrix_id'] != matrix_id]
    write_rows(results_csv, keep_rows)

    for run_id in unique(row['run_id'] for row in rows if row['matrix_id'] == matrix_id):
        if not run_id:
            continue
        src = runs_root / run_id
        if src.exists() and safe_relative(src, runs_root):
            shutil.rmtree(src)

    if config_prefix:
        for cfg in unique(row['config_path'] for row in rows if row['matrix_id'] == matrix_id):
            if not cfg:
                continue
            src = Path(cfg)
            if src.exists() and safe_relative(src, config_prefix):
                src.unlink()


def parse_args():
    parser = argparse.ArgumentParser(description='Archive and clean matrix experiment artifacts')
    parser.add_argument('--matrix-id', required=True, help='Matrix identifier to process')
    parser.add_argument('--results-csv', default='logs/matrix_results.csv')
    parser.add_argument('--runs-root', default='logs/runs')
    parser.add_argument('--config-prefix', default='logs/generated_configs', help='Only configs under this path are touched')
    parser.add_argument('--archive-root', default='logs/archive')
    parser.add_argument('--matrix-spec', help='Optional spec file to include in archive')
    parser.add_argument('--archive', action='store_true', help='Copy data into archive directory')
    parser.add_argument('--no-archive', dest='archive', action='store_false', help='Skip archive step')
    parser.add_argument('--cleanup', action='store_true', help='Delete matching runs/configs and drop rows from CSV')
    parser.add_argument('--skip-run-copy', action='store_true', help='Do not copy run directories during archive')
    parser.add_argument('--skip-config-copy', action='store_true', help='Do not copy generated configs during archive')
    parser.set_defaults(archive=True)
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.archive and not args.cleanup:
        raise SystemExit('Nothing to do: specify --archive and/or --cleanup')

    results_csv = Path(args.results_csv)
    rows = load_rows(results_csv)
    if not rows:
        print('No matrix results found; nothing to process.')
        return

    matrix_rows = [row for row in rows if row['matrix_id'] == args.matrix_id]
    if not matrix_rows:
        print(f"No entries for matrix_id={args.matrix_id} in {results_csv}")
        return

    runs_root = Path(args.runs_root)
    config_prefix = Path(args.config_prefix) if args.config_prefix else None

    if args.archive:
        dest = archive_data(
            args.matrix_id,
            rows,
            runs_root=runs_root,
            archive_root=Path(args.archive_root),
            config_prefix=config_prefix,
            matrix_spec=Path(args.matrix_spec) if args.matrix_spec else None,
            copy_runs=not args.skip_run_copy,
            copy_configs=not args.skip_config_copy,
        )
        print(f"Archived matrix '{args.matrix_id}' to {dest}")

    if args.cleanup:
        cleanup_data(
            args.matrix_id,
            rows,
            runs_root=runs_root,
            config_prefix=config_prefix,
            results_csv=results_csv,
        )
        print(f"Removed matrix '{args.matrix_id}' data from active logs")


if __name__ == '__main__':
    main()
