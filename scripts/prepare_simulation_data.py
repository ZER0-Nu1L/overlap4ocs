#!/usr/bin/env python3
"""Prepare reproducible CSV inputs for paper figure generation."""
from __future__ import annotations

import argparse
import hashlib
import math
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd

CSV_HEADER = [
    "timestamp",
    "matrix_id",
    "run_id",
    "config_path",
    "algorithm",
    "message_mib",
    "solver",
    "solver_gap",
    "solver_time_limit",
    "k",
    "T_reconf",
    "T_lat",
    "B",
    "p",
    "status",
    "returncode",
    "duration_seconds",
    "optimized_cct",
    "baseline_cct",
    "oneshot_cct",
    "ideal_cct",
    "improvement_over_baseline_pct",
    "metrics_path",
    "hash",
]

EXP13_MSG_SIZES_MIB = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 512.0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare simulation CSVs used by scripts/simulation_fig.ipynb and scripts/simulation_fig.py"
    )
    parser.add_argument(
        "--target",
        choices=["all", "exp1.1", "exp1.3-ar", "exp1.3-a2a"],
        default="all",
        help="Which dataset to prepare",
    )
    parser.add_argument("--logs-dir", default="logs", help="Directory containing matrix result CSV files")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip missing source CSVs instead of failing",
    )
    return parser.parse_args()


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in CSV_HEADER:
        if column not in out.columns:
            out[column] = np.nan
    return out[CSV_HEADER]


def load_csv(path: Path, allow_missing: bool = False) -> pd.DataFrame:
    if not path.exists():
        if allow_missing:
            print(f"[WARN] Missing source CSV, skipped: {path}")
            return pd.DataFrame(columns=CSV_HEADER)
        raise FileNotFoundError(f"Missing required source CSV: {path}")
    return ensure_columns(pd.read_csv(path))


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("message_mib", "k", "B", "p", "T_reconf", "T_lat", "optimized_cct", "baseline_cct", "oneshot_cct", "ideal_cct"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def dedupe_and_sort(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_types(df)
    if out.empty:
        return out
    if "hash" in out.columns:
        out = out.dropna(subset=["hash"]).drop_duplicates(subset=["hash"], keep="last")
    out = out.sort_values(by=["algorithm", "k", "p", "B", "message_mib", "timestamp"], kind="stable")
    return out.reset_index(drop=True)


def write_csv(df: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out = ensure_columns(dedupe_and_sort(df))
    out.to_csv(output_path, index=False)
    print(f"[OK] Wrote {len(out)} rows -> {output_path}")
    return output_path


def combine_csvs(paths: Iterable[Path], allow_missing: bool) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for path in paths:
        frame = load_csv(path, allow_missing=allow_missing)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=CSV_HEADER)
    return pd.concat(frames, ignore_index=True)


def prepare_exp11(logs_dir: Path, allow_missing: bool) -> Path:
    src_paths = [
        logs_dir / "matrix_results-exp1.1-hd+bruck-1.csv",
        logs_dir / "matrix_results-exp1.1-pair-1.csv",
        logs_dir / "matrix_results-exp1.1-hd+bruck-2.csv",
        logs_dir / "matrix_results-exp1.1-pair-2.csv",
    ]
    merged = combine_csvs(src_paths, allow_missing=allow_missing)
    return write_csv(merged, logs_dir / "results-exp1.1.csv")


def nccl_optimal_k(message_size_mib: float, p: int) -> int:
    message_size_bytes = message_size_mib * 1024 * 1024
    if message_size_bytes < 16 * 1024:
        base_chunk_size_bytes = 128 * 1024
    elif message_size_bytes < 1 * 1024 * 1024:
        base_chunk_size_bytes = 256 * 1024
    else:
        base_chunk_size_bytes = 512 * 1024

    max_parallelism = min(p, 8)
    adjusted_chunk_size_mib = (base_chunk_size_bytes * max_parallelism) / (1024 * 1024)
    chunk_num = max(1, min(p, int(message_size_mib / adjusted_chunk_size_mib)))
    if chunk_num > 1:
        chunk_num = 2 ** int(math.log2(chunk_num))
    return chunk_num


def calc_dbt(msg_size_mib: float, chunk_num: int, p: int, k: int, B: float, T_reconf: float, T_lat: float) -> float:
    chunk_size_mib = msg_size_mib / chunk_num
    steps = 2 * math.ceil(math.log2(p)) + 2 * (chunk_num - 1)
    time_per_step = T_lat + (chunk_size_mib / 2) / k / B
    return T_reconf + steps * time_per_step


def calc_dbt_time(m_mib: float, chunk_num: int, p: int, B: float, T_reconf: float, T_lat: float) -> float:
    n_chunks = chunk_num
    chunk_size = m_mib / n_chunks
    steps = 2 * math.ceil(math.log2(p)) + 2 * (n_chunks - 1)
    time_per_step = T_lat + (chunk_size / 2) / chunk_num / B
    return T_reconf + steps * time_per_step


def compute_row_hash(row: dict) -> str:
    # Keep deterministic hash independent from runtime timestamp.
    key = "|".join(
        str(row.get(name, ""))
        for name in ("algorithm", "message_mib", "k", "p", "B", "T_reconf", "T_lat", "optimized_cct", "solver")
    )
    return hashlib.sha1(key.encode()).hexdigest()


def build_analytical_exp13_ar_rows(k: int, p: int, B: float, T_reconf: float, T_lat: float) -> pd.DataFrame:
    rows = []
    ts = datetime.now().isoformat(timespec="seconds")

    for m in EXP13_MSG_SIZES_MIB:
        t_ar_ring = T_reconf + (p - 1) * T_lat + m / k / B * (p - 1) / p
        t_ar_dbt = calc_dbt(m, p, p, k, B, T_reconf, T_lat)

        _ = nccl_optimal_k(m, p)  # Keep notebook-equivalent path explicit, even if final value uses brute-force min.
        chunk_num_candidates = [2**i for i in range(0, int(math.log2(p)) + 1)]
        times = [calc_dbt_time(m, chunk_num, p, B, T_reconf, T_lat) for chunk_num in chunk_num_candidates]
        t_ar_dbt_pipe = float(times[int(np.argmin(times))])

        for alg, cct in (("ar_ring", t_ar_ring), ("ar_dbt", t_ar_dbt), ("ar_dbt_pipe", t_ar_dbt_pipe)):
            row = {
                "timestamp": ts,
                "matrix_id": f"exp1.3-{alg.replace('_', '-')}",
                "run_id": f"analytical_exp1.3-ar_{alg}_k{k}_p{p}_m{str(m).replace('.', 'p')}",
                "config_path": "analytical",
                "algorithm": alg,
                "message_mib": m,
                "solver": "analytical",
                "solver_gap": np.nan,
                "solver_time_limit": np.nan,
                "k": k,
                "T_reconf": T_reconf,
                "T_lat": T_lat,
                "B": B,
                "p": p,
                "status": "success",
                "returncode": 0,
                "duration_seconds": np.nan,
                "optimized_cct": cct,
                "baseline_cct": cct,
                "oneshot_cct": cct,
                "ideal_cct": cct,
                "improvement_over_baseline_pct": 0.0,
                "metrics_path": "analytical",
            }
            row["hash"] = compute_row_hash(row)
            rows.append(row)
    return ensure_columns(pd.DataFrame(rows))


def prepare_exp13_ar(logs_dir: Path, exp11_path: Path, allow_missing: bool) -> Path:
    ar_matrix = load_csv(logs_dir / "matrix_results-exp1.3-ar.csv", allow_missing=allow_missing)
    exp11_df = load_csv(exp11_path, allow_missing=allow_missing)

    ar_matrix = normalize_types(ar_matrix)
    exp11_df = normalize_types(exp11_df)

    ar_rb = ar_matrix[(ar_matrix["status"] == "success") & (ar_matrix["algorithm"] == "ar_recursive-doubling")]
    ar_hd = exp11_df[
        (exp11_df["status"] == "success")
        & (exp11_df["algorithm"] == "ar_having-doubling")
        & (exp11_df["k"] == 8)
        & (exp11_df["p"] == 256)
        & (np.isclose(exp11_df["B"], 12.5))
    ]

    analytical = build_analytical_exp13_ar_rows(k=8, p=256, B=12.5, T_reconf=0.2, T_lat=0.02)
    merged = pd.concat([ensure_columns(ar_rb), ensure_columns(ar_hd), analytical], ignore_index=True)
    return write_csv(merged, logs_dir / "results-exp1.3-ar.csv")


def prepare_exp13_a2a(logs_dir: Path, exp11_path: Path, allow_missing: bool) -> tuple[Path, Path]:
    pair_256 = load_csv(logs_dir / "matrix_results-exp1.3-a2a.csv", allow_missing=allow_missing)
    bruck_9 = load_csv(logs_dir / "matrix_results-exp1.3-a2a-9.csv", allow_missing=allow_missing)
    exp11_df = load_csv(exp11_path, allow_missing=allow_missing)

    pair_256 = normalize_types(pair_256)
    bruck_9 = normalize_types(bruck_9)
    exp11_df = normalize_types(exp11_df)

    pair_success = pair_256[
        (pair_256["status"] == "success")
        & (pair_256["algorithm"] == "a2a_pairwise")
        & (pair_256["k"] == 8)
        & (pair_256["p"] == 256)
        & (np.isclose(pair_256["B"], 12.5))
    ]
    bruck_256 = exp11_df[
        (exp11_df["status"] == "success")
        & (exp11_df["algorithm"] == "a2a_bruck")
        & (exp11_df["k"] == 8)
        & (exp11_df["p"] == 256)
        & (np.isclose(exp11_df["B"], 12.5))
    ]
    bruck_9_success = bruck_9[(bruck_9["status"] == "success") & (bruck_9["algorithm"] == "a2a_bruck")]

    out_256 = write_csv(
        pd.concat([ensure_columns(pair_success), ensure_columns(bruck_256)], ignore_index=True),
        logs_dir / "results-exp1.3-a2a.csv",
    )
    out_9 = write_csv(ensure_columns(bruck_9_success), logs_dir / "results-exp1.3-a2a-9.csv")
    return out_256, out_9


def main() -> None:
    args = parse_args()
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    exp11_path = logs_dir / "results-exp1.1.csv"
    if args.target in ("all", "exp1.1"):
        exp11_path = prepare_exp11(logs_dir, allow_missing=args.allow_missing)

    if args.target in ("all", "exp1.3-ar"):
        if not exp11_path.exists():
            exp11_path = prepare_exp11(logs_dir, allow_missing=args.allow_missing)
        prepare_exp13_ar(logs_dir, exp11_path, allow_missing=args.allow_missing)

    if args.target in ("all", "exp1.3-a2a"):
        if not exp11_path.exists():
            exp11_path = prepare_exp11(logs_dir, allow_missing=args.allow_missing)
        prepare_exp13_a2a(logs_dir, exp11_path, allow_missing=args.allow_missing)


if __name__ == "__main__":
    main()
