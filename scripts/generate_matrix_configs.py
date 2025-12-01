#!/usr/bin/env python3
"""Generate instance configs from a matrix spec."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List

import toml


def load_matrix_spec(path: Path) -> dict:
    with path.open() as f:
        spec = toml.load(f)
    required = ["matrix_id", "topology", "message_sizes_mib", "algorithms"]
    for key in required:
        if key not in spec:
            raise ValueError(f"Missing '{key}' in matrix spec {path}")
    return spec


def parse_message_size(value: float | int | str) -> Decimal:
    """Return a Decimal representation of the MiB value."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid message size '{value}'") from exc


def format_message_label(value: Decimal) -> str:
    """Build a filename-safe suffix that preserves fractional values."""
    if value == value.to_integral():
        return f"{int(value):06d}"
    text = format(value.normalize(), 'f').rstrip('0').rstrip('.')
    if not text:
        text = "0"
    return text.replace('.', '_')


def to_instance(
    topology: dict,
    algorithm: str,
    message_mib: float,
    solver: str,
    solver_gap: float | None = None,
    solver_time_limit: float | None = None,
) -> dict:
    message_value = parse_message_size(message_mib)
    instance = dict(topology)
    instance["algorithm"] = algorithm
    instance["solver"] = solver
    if solver_gap is not None:
        instance["solver_gap"] = solver_gap
    if solver_time_limit is not None:
        instance["solver_time_limit"] = solver_time_limit
    if message_value == message_value.to_integral():
        instance["m"] = int(message_value)
    else:
        instance["m"] = float(message_value)
    return instance


def config_filename(matrix_id: str, algorithm: str, message_mib: float) -> str:
    msg = format_message_label(parse_message_size(message_mib))
    return f"{matrix_id}_{algorithm}_m{msg}.toml"


def write_configs(spec: dict, out_dir: Path, overwrite: bool) -> List[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    solver = spec.get("solver", "pulp")
    solver_opts = spec.get("solver_options", {})
    solver_gap = spec.get("solver_gap", solver_opts.get("gap"))
    solver_time_limit = spec.get("solver_time_limit", solver_opts.get("time_limit"))
    for algorithm in spec["algorithms"]:
        for msg in spec["message_sizes_mib"]:
            instance = to_instance(
                spec["topology"],
                algorithm,
                msg,
                solver,
                solver_gap=solver_gap,
                solver_time_limit=solver_time_limit,
            )
            fname = config_filename(spec["matrix_id"], algorithm, msg)
            cfg_path = out_dir / fname
            if cfg_path.exists() and not overwrite:
                raise FileExistsError(f"Config already exists: {cfg_path} (use --overwrite)")
            with cfg_path.open('w') as f:
                toml.dump(instance, f)
            entries.append({
                "config": str(cfg_path),
                "algorithm": algorithm,
                "message_mib": msg,
                "solver": solver,
                "hash": hashlib.sha1(json.dumps(instance, sort_keys=True).encode()).hexdigest()
            })
    index_path = out_dir / "index.json"
    with index_path.open('w') as f:
        json.dump(entries, f, indent=2)
    return entries


def parse_args():
    parser = argparse.ArgumentParser(description="Generate configs for matrix experiments")
    parser.add_argument('--matrix', required=True, help='Matrix spec toml path')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing configs if present')
    return parser.parse_args()


def main():
    args = parse_args()
    spec = load_matrix_spec(Path(args.matrix))
    out_dir = Path(spec.get('output', {}).get('config_dir', 'logs/generated_configs'))
    entries = write_configs(spec, out_dir, args.overwrite)
    print(f"Generated {len(entries)} configs under {out_dir}")


if __name__ == '__main__':
    main()
