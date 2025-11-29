#!/usr/bin/env python3
"""Generate instance configs from a matrix spec."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def to_instance(topology: dict, algorithm: str, message_mib: float, solver: str) -> dict:
    instance = dict(topology)
    instance["algorithm"] = algorithm
    instance["solver"] = solver
    instance["m"] = int(message_mib)
    return instance


def config_filename(matrix_id: str, algorithm: str, message_mib: float) -> str:
    msg = f"{message_mib:06.0f}".replace('.', '_')
    return f"{matrix_id}_{algorithm}_m{msg}.toml"


def write_configs(spec: dict, out_dir: Path, overwrite: bool) -> List[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    solver = spec.get("solver", "pulp")
    for algorithm in spec["algorithms"]:
        for msg in spec["message_sizes_mib"]:
            instance = to_instance(spec["topology"], algorithm, msg, solver)
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
