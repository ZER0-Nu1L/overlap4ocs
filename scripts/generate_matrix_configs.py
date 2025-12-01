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
from itertools import product
from decimal import Decimal


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


def expand_topologies(topology: dict) -> list:
    """Expand topology definitions into a list of (name, topo) tuples.

    Supports two forms of `topology` in the matrix spec:
    1. Mapping of scalar or list values, e.g.:
         {"k": [2,4], "p": [4,8]}
       -> Cartesian product of keys -> combos with name=None.

    2. Mapping of subtables (explicit pairs), e.g.:
         {"pair1": {"k":2, "B":50}, "pair2": {...}}
       -> returns [("pair1", {...}), ("pair2", {...})]

    Return value: list of (name_or_none, topo_dict).
    """
    def _coerce_scalar(v):
        # If value is a numeric-like string, convert to int or float.
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                try:
                    return float(v)
                except ValueError:
                    return v
        return v

    # Detect explicit subtable style: any value is a dict
    if any(isinstance(v, dict) for v in topology.values()):
        combos = []
        for name, sub in topology.items():
            if isinstance(sub, dict):
                # coerce numeric-like strings inside subtable
                coerced = {k: _coerce_scalar(val) for k, val in sub.items()}
                combos.append((name, coerced))
        return combos

    # Otherwise, treat topology as mapping of scalars/lists and expand
    keys = list(topology.keys())
    values_list = []
    for k in keys:
        v = topology[k]
        if isinstance(v, list) or isinstance(v, tuple):
            # coerce elements in lists (in case they are numeric strings)
            values_list.append([_coerce_scalar(el) for el in v])
        else:
            values_list.append([_coerce_scalar(v)])

    combos = []
    for prod in product(*values_list):
        combos.append((None, {k: val for k, val in zip(keys, prod)}))
    return combos


def _format_value_label(v) -> str:
    # Produce a filename-safe representation for topology values
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        # replace decimal point with 'p' to avoid extra dots in filename
        return str(v).replace('.', 'p')
    if isinstance(v, int):
        return str(v)
    return str(v).replace(' ', '_')


def format_topology_label(topo: dict) -> str:
    parts = []
    # sort keys for stable ordering
    for k in sorted(topo.keys()):
        parts.append(f"{k}={_format_value_label(topo[k])}")
    return "__" + "_".join(parts) if parts else ""


def config_filename(matrix_id: str, algorithm: str, message_mib: float, topo: dict | None = None, topo_name: str | None = None) -> str:
    msg = format_message_label(parse_message_size(message_mib))
    topo_label = format_topology_label(topo) if topo else ""
    name_label = f"_{topo_name}" if topo_name else ""
    return f"{matrix_id}_{algorithm}{name_label}{topo_label}_m{msg}.toml"


def write_configs(spec: dict, out_dir: Path, overwrite: bool) -> List[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    solver = spec.get("solver", "pulp")
    solver_opts = spec.get("solver_options", {})
    solver_gap = spec.get("solver_gap", solver_opts.get("gap"))
    solver_time_limit = spec.get("solver_time_limit", solver_opts.get("time_limit"))

    # Support topology sweep: expand topology values that are lists into combinations
    topology = spec["topology"]
    topology_combos = expand_topologies(topology)

    for topo_name, topo in topology_combos:
        for algorithm in spec["algorithms"]:
            for msg in spec["message_sizes_mib"]:
                instance = to_instance(
                    topo,
                    algorithm,
                    msg,
                    solver,
                    solver_gap=solver_gap,
                    solver_time_limit=solver_time_limit,
                )
                fname = config_filename(spec["matrix_id"], algorithm, msg, topo=topo, topo_name=topo_name)
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
