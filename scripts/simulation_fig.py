#!/usr/bin/env python3
"""Generate paper figures from matrix result CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import ConnectionPatch
from matplotlib.ticker import FuncFormatter

COLORS = {
    "strawman": "#4f669f",
    "swot": "#ecbc4a",
    "ideal": "#5ea195",
    "oneshot": "#c73934",
}

ALGO_LABELS = {
    "rs_having-doubling": "ReduceScatter-Rabenseifner's",
    "ar_having-doubling": "AllReduce-Rabenseifner's",
    "a2a_bruck": "AlltoAll-Bruck",
    "a2a_pairwise": "AlltoAll-Pairwise",
    "ar_recursive-doubling": "AllReduce-Recursive-Doubling",
    "ar_ring": "AllReduce-Ring",
    "ar_dbt": "AllReduce-DBT",
    "ar_dbt_pipe": "AllReduce-DBT-Pipe",
}

ALGO_ABBR = {
    "ar_having-doubling": "HD",
    "ar_recursive-doubling": "RD",
    "ar_ring": "R",
    "ar_dbt": "D",
    "ar_dbt_pipe": "DP",
    "a2a_pairwise": "P",
    "a2a_bruck": "B",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible paper figures without running notebook cells manually."
    )
    parser.add_argument(
        "--exp11-csv",
        default="logs/results-exp1.1.csv",
        help="CSV path for exp1.1 data",
    )
    parser.add_argument(
        "--exp12-hd-bruck-csv",
        default="logs/matrix_results-exp1.2-hd+bruck.csv",
        help="CSV path for exp1.2 (AllReduce + Bruck)",
    )
    parser.add_argument(
        "--exp12-pair-csv",
        default="logs/matrix_results-exp1.2-pair.csv",
        help="CSV path for exp1.2 pairwise",
    )
    parser.add_argument(
        "--exp13-ar-csv",
        default="logs/results-exp1.3-ar.csv",
        help="CSV path for exp1.3 AllReduce comparison",
    )
    parser.add_argument(
        "--exp13-a2a-9-csv",
        default="logs/results-exp1.3-a2a-9.csv",
        help="CSV path for exp1.3 A2A (p=9)",
    )
    parser.add_argument(
        "--exp13-a2a-256-csv",
        default="logs/results-exp1.3-a2a.csv",
        help="CSV path for exp1.3 A2A (p=256)",
    )
    parser.add_argument(
        "--exp21-csv",
        default="logs/matrix_results-m32_sweep_msg+k-B.csv",
        help="CSV path for exp2.1 (impact of k/B)",
    )
    parser.add_argument(
        "--exp22-csv",
        default="logs/matrix_results-m32_sweep_msg+Tr.csv",
        help="CSV path for exp2.2 (impact of T_reconf)",
    )
    parser.add_argument(
        "--output-dir",
        default="figures/paper",
        help="Output directory for generated figures",
    )
    parser.add_argument(
        "--skip-exp11", action="store_true", help="Skip exp1.1 figure generation"
    )
    parser.add_argument(
        "--skip-exp12", action="store_true", help="Skip exp1.2 figure generation"
    )
    parser.add_argument(
        "--skip-exp13", action="store_true", help="Skip exp1.3 figure generation"
    )
    parser.add_argument(
        "--skip-exp21", action="store_true", help="Skip exp2.1 figure generation"
    )
    parser.add_argument(
        "--skip-exp22", action="store_true", help="Skip exp2.2 figure generation"
    )
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Write exp1.1 text summary to output directory",
    )
    return parser.parse_args()


def maybe_alternate_csv(path: Path) -> Path:
    if path.exists():
        return path
    # Compatibility with historical filename typo: +k-b vs +k-B.
    name = path.name
    if "+k-B" in name:
        alt = path.with_name(name.replace("+k-B", "+k-b"))
        if alt.exists():
            return alt
    if "+k-b" in name:
        alt = path.with_name(name.replace("+k-b", "+k-B"))
        if alt.exists():
            return alt
    return path


def load_results(path: Path) -> pd.DataFrame:
    path = maybe_alternate_csv(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing CSV: {path}. Run scripts/prepare_simulation_data.py or matrix_runner first."
        )
    df = pd.read_csv(path)
    if "status" in df.columns:
        df = df[df["status"] == "success"].copy()
    for col in (
        "message_mib",
        "p",
        "k",
        "B",
        "T_reconf",
        "solver_time_limit",
        "optimized_cct",
        "baseline_cct",
        "oneshot_cct",
        "ideal_cct",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clamp_optimized_cct(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"optimized_cct", "baseline_cct"}.issubset(out.columns):
        mask = out["optimized_cct"] > out["baseline_cct"]
        out.loc[mask, "optimized_cct"] = out.loc[mask, "baseline_cct"]
    if {"optimized_cct", "oneshot_cct"}.issubset(out.columns):
        mask = out["oneshot_cct"].notna() & (out["optimized_cct"] > out["oneshot_cct"])
        out.loc[mask, "optimized_cct"] = out.loc[mask, "oneshot_cct"]
    return out


def format_msg_size_label(message_mib: float, multiline: bool = False) -> str:
    msg_kib = message_mib * 1024
    sep = "\n" if multiline else ""
    if msg_kib < 1024:
        return f"{msg_kib:.0f}{sep}KB"
    if message_mib.is_integer():
        return f"{message_mib:.0f}{sep}MB"
    return f"{message_mib:.1f}{sep}MB"


def save_fig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"[OK] Figure written: {path}")


def plot_exp11_focus_figure(
    df: pd.DataFrame,
    config: dict[str, float | str],
    out_file: Path,
    zoom_idx_range: tuple[int, int],
    manual_ylim: float | None,
    inset_position: list[float],
) -> None:
    subdf = df[
        (df["algorithm"] == config["alg"])
        & (df["p"] == config["p"])
        & (df["k"] == config["k"])
        & (np.isclose(df["B"], float(config["B"])))
    ].copy()
    subdf = subdf.sort_values("message_mib").reset_index(drop=True)
    if subdf.empty:
        raise ValueError(f"No exp1.1 data for config={config}")

    y_straw = subdf["baseline_cct"].replace({0: np.nan}).values
    y_swot = subdf["optimized_cct"].replace({0: np.nan}).values
    y_ideal = subdf["ideal_cct"].replace({0: np.nan}).values
    y_oneshot = subdf["oneshot_cct"].replace({0: np.nan}).values
    x = np.arange(len(subdf))
    x_labels = [
        format_msg_size_label(float(v), multiline=True)
        for v in subdf["message_mib"].values
    ]

    fig = plt.figure(figsize=(11, 7), dpi=100)
    ax_main = fig.add_axes([0.1, 0.1, 0.85, 0.8])

    ax_main.plot(
        x, y_ideal, c="#d5d6d5", marker="s", lw=2.5, ms=8, label="Ideal", ls="--"
    )
    if not np.all(np.isnan(y_oneshot)):
        ax_main.plot(
            x,
            y_oneshot,
            c=COLORS["oneshot"],
            marker="+",
            lw=2.5,
            ms=8,
            label="One-shot",
        )
    ax_main.plot(
        x, y_straw, c=COLORS["strawman"], marker="D", lw=2.5, ms=8, label="Strawman-ICR"
    )
    ax_main.plot(
        x, y_swot, c=COLORS["swot"], marker="o", lw=2.5, ms=8, label="SWOT (Proposed)"
    )

    ax_main.set_xticks(x)
    ax_main.set_xticklabels(x_labels, fontsize=16)
    ax_main.set_xlabel("Message Size", fontsize=22)
    ax_main.set_ylabel("CCT (ms)", fontsize=22, fontweight="bold")

    if manual_ylim is None:
        all_data = [y_straw, y_swot, y_ideal]
        if not np.all(np.isnan(y_oneshot)):
            all_data.append(y_oneshot)
        y_max = np.nanmax([np.nanmax(d) for d in all_data])
        ax_main.set_ylim(0, y_max * 1.2)
    else:
        ax_main.set_ylim(0, manual_ylim)

    title = f"{ALGO_LABELS.get(str(config['alg']), str(config['alg']))} (P={int(config['p'])}, K={int(config['k'])})"
    ax_main.set_title(title, fontsize=24, pad=20)
    ax_main.grid(True, linestyle="-", alpha=0.3)
    ax_main.legend(
        loc="upper left",
        bbox_to_anchor=(0.02, 0.98),
        fontsize=16,
        frameon=True,
        edgecolor="gray",
        facecolor="white",
        framealpha=0.95,
    )

    zoom_start, zoom_end = zoom_idx_range
    zoom_end = min(zoom_end, len(x))
    x_zoom = x[zoom_start:zoom_end]
    ax_ins = fig.add_axes(inset_position)
    ax_ins.plot(
        x_zoom, y_ideal[zoom_start:zoom_end], c="#d5d6d5", marker="s", lw=2, ls="--"
    )
    if not np.all(np.isnan(y_oneshot)):
        ax_ins.plot(
            x_zoom,
            y_oneshot[zoom_start:zoom_end],
            c=COLORS["oneshot"],
            marker="+",
            lw=2,
        )
    ax_ins.plot(
        x_zoom, y_straw[zoom_start:zoom_end], c=COLORS["strawman"], marker="D", lw=2
    )
    ax_ins.plot(x_zoom, y_swot[zoom_start:zoom_end], c=COLORS["swot"], marker="o", lw=2)
    ax_ins.set_xticks(x_zoom)
    ax_ins.set_xticklabels(x_labels[zoom_start:zoom_end], fontsize=12)
    ax_ins.set_ylabel("CCT (ms)", fontsize=14)
    ax_ins.set_title("Small Message Zoom", fontsize=14)
    ax_ins.grid(True, alpha=0.3)

    con1 = ConnectionPatch(
        xyA=(0, 0),
        xyB=(zoom_start, 0),
        coordsA="axes fraction",
        coordsB="data",
        axesA=ax_ins,
        axesB=ax_main,
        color="gray",
        linestyle="--",
        alpha=0.5,
    )
    con2 = ConnectionPatch(
        xyA=(1, 0),
        xyB=(zoom_end - 1, 0),
        coordsA="axes fraction",
        coordsB="data",
        axesA=ax_ins,
        axesB=ax_main,
        color="gray",
        linestyle="--",
        alpha=0.5,
    )
    fig.add_artist(con1)
    fig.add_artist(con2)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Figure written: {out_file}")


def plot_exp11_suite(df: pd.DataFrame, output_dir: Path) -> None:
    configs = [
        (
            {"alg": "rs_having-doubling", "p": 256, "k": 8, "B": 12.5},
            "exp1.1-rs-hd.pdf",
            (2, 9),
            45.0,
            [0.2, 0.25, 0.25, 0.3],
        ),
        (
            {"alg": "ar_having-doubling", "p": 256, "k": 8, "B": 12.5},
            "exp1.1-ar-hd.pdf",
            (2, 9),
            60.0,
            [0.2, 0.25, 0.25, 0.3],
        ),
        (
            {"alg": "a2a_bruck", "p": 256, "k": 8, "B": 12.5},
            "exp1.1-a2a-bruck.pdf",
            (1, 7),
            90.0,
            [0.2, 0.25, 0.25, 0.3],
        ),
        (
            {"alg": "a2a_pairwise", "p": 9, "k": 8, "B": 12.5},
            "exp1.1-a2a-pair.pdf",
            (2, 9),
            10.0,
            [0.2, 0.32, 0.25, 0.28],
        ),
    ]
    for cfg, filename, zoom_range, manual_ylim, inset_pos in configs:
        plot_exp11_focus_figure(
            df=df,
            config=cfg,
            out_file=output_dir / filename,
            zoom_idx_range=zoom_range,
            manual_ylim=manual_ylim,
            inset_position=inset_pos,
        )


def build_exp11_summary(df: pd.DataFrame) -> str:
    alg_order = [
        "rs_having-doubling",
        "ar_having-doubling",
        "a2a_pairwise",
        "a2a_bruck",
    ]
    base = df[df["algorithm"].isin(alg_order)].copy()
    if base.empty:
        return "No exp1.1 rows matched summary algorithm set."

    vs_straw = base.groupby("algorithm")["improvement_over_baseline_pct"].agg(
        ["min", "max"]
    )
    valid = base[(base["oneshot_cct"] > 0) & base["oneshot_cct"].notna()].copy()
    valid["impr_vs_oneshot"] = (
        (valid["oneshot_cct"] - valid["optimized_cct"]) / valid["oneshot_cct"] * 100
    )
    vs_oneshot = valid.groupby("algorithm")["impr_vs_oneshot"].agg(["min", "max"])

    lines = ["exp1.1 summary", "", "Improvement vs One-shot:"]
    for alg in alg_order:
        if alg in vs_oneshot.index:
            lines.append(
                f"- {alg}: {vs_oneshot.loc[alg, 'min']:.1f}% to {vs_oneshot.loc[alg, 'max']:.1f}%"
            )
    lines.append("")
    lines.append("Improvement vs Strawman:")
    for alg in alg_order:
        if alg in vs_straw.index:
            lines.append(
                f"- {alg}: {vs_straw.loc[alg, 'min']:.1f}% to {vs_straw.loc[alg, 'max']:.1f}%"
            )
    return "\n".join(lines)


def plot_exp12_curve(df: pd.DataFrame, algorithm: str, out_file: Path) -> None:
    subdf = df[
        (df["algorithm"] == algorithm) & (df["k"] == 4) & (np.isclose(df["B"], 25))
    ].copy()
    subdf = subdf.sort_values("p")
    if subdf.empty:
        raise ValueError(f"No exp1.2 data for {algorithm}")

    x = subdf["p"].tolist()
    y_straw = subdf["baseline_cct"].tolist()
    y_swot = subdf["optimized_cct"].tolist()
    y_oneshot = subdf["oneshot_cct"].tolist()
    y_ideal = subdf["ideal_cct"].tolist()
    mask = np.array([v is not None and not pd.isna(v) for v in y_oneshot])

    plt.figure(figsize=(8, 5))
    plt.plot(
        x,
        y_straw,
        linestyle="solid",
        c=COLORS["strawman"],
        marker="o",
        label="Strawman-ICR",
    )
    plt.plot(x, y_swot, linestyle="solid", c=COLORS["swot"], marker="D", label="SWOT")
    if np.any(mask):
        plt.plot(
            np.array(x)[mask],
            np.array(y_oneshot)[mask],
            linestyle="solid",
            c=COLORS["oneshot"],
            marker="X",
            label="One-shot",
        )
    plt.plot(x, y_ideal, linestyle="dashed", c="#d5d6d5", marker="s", label="Ideal")

    if np.any(mask):
        last_idx = np.where(mask)[0][-1]
        y_ref = (
            max(y_oneshot[last_idx], y_straw[last_idx])
            if not pd.isna(y_oneshot[last_idx])
            else y_straw[last_idx]
        )
        plt.annotate(
            "One-shot unsupported\nfor larger clusters",
            xy=(x[last_idx], y_oneshot[last_idx]),
            xytext=(x[last_idx], y_ref * 1.25),
            arrowprops=dict(arrowstyle="->", color="#766f6f", linewidth=1),
            color=COLORS["oneshot"],
            fontsize=11,
        )

    plt.xlabel("Number of Nodes")
    plt.ylabel("CCT(ms)")
    if algorithm != "a2a_pairwise":
        plt.xscale("log")
    plt.xticks(x, [str(v) for v in x])
    plt.grid(axis="both", which="major", color="#d5d6d5", linewidth=0.5)
    plt.tight_layout()
    plt.legend()
    save_fig(out_file)


def prepare_data_best(
    df: pd.DataFrame, fixed_params: dict[str, float], alg_candidates: list[str]
) -> pd.DataFrame:
    subdf = df[
        (df["p"] == fixed_params["p"])
        & (df["k"] == fixed_params["k"])
        & (np.isclose(df["B"], fixed_params["B"]))
        & (df["algorithm"].isin(alg_candidates))
    ].copy()
    if subdf.empty:
        raise ValueError(
            f"No data found for params={fixed_params} and algs={alg_candidates}"
        )

    unique_msgs = sorted(subdf["message_mib"].dropna().unique())
    rows = []
    for msg in unique_msgs:
        part = subdf[subdf["message_mib"] == msg]
        if part.empty:
            continue
        swot_idx = part["optimized_cct"].idxmin()
        swot_val = float(part.loc[swot_idx, "optimized_cct"])
        swot_alg = str(part.loc[swot_idx, "algorithm"])
        swot_label = ALGO_ABBR.get(swot_alg, "?")

        straw_val = (
            float(part["baseline_cct"].min())
            if part["baseline_cct"].notna().any()
            else np.nan
        )
        ideal_val = (
            float(part["ideal_cct"].min())
            if part["ideal_cct"].notna().any()
            else np.nan
        )
        oneshot_val = (
            float(part["oneshot_cct"].min())
            if part["oneshot_cct"].notna().any()
            else np.nan
        )

        candidates = [v for v in (straw_val, oneshot_val) if pd.notna(v)]
        gain_pct = np.nan
        if candidates and pd.notna(swot_val) and swot_val > 0:
            gain_pct = (min(candidates) / swot_val - 1) * 100

        rows.append(
            {
                "message_mib": float(msg),
                "swot_cct": swot_val,
                "swot_label": swot_label,
                "straw_cct": straw_val,
                "ideal_cct": ideal_val,
                "oneshot_cct": oneshot_val,
                "gain_pct": gain_pct,
            }
        )
    return pd.DataFrame(rows)


def draw_comprehensive_plot(
    plot_df: pd.DataFrame,
    target_config: dict[str, float],
    out_file: Path,
    zoom_range: tuple[int, int],
    gain_range: tuple[int, int],
    manual_ylim: float | None = None,
) -> None:
    x = np.arange(len(plot_df))
    x_labels = [
        format_msg_size_label(float(v), multiline=True) for v in plot_df["message_mib"]
    ]

    y_swot = plot_df["swot_cct"].values
    y_straw = plot_df["straw_cct"].values
    y_ideal = plot_df["ideal_cct"].values
    y_oneshot = plot_df["oneshot_cct"].values
    y_gain = plot_df["gain_pct"].values
    labels = plot_df["swot_label"].values

    fig = plt.figure(figsize=(11, 8), dpi=100)
    ax_main = fig.add_axes([0.1, 0.1, 0.85, 0.8])

    lw, ms = 2.5, 9
    ax_main.plot(
        x, y_swot, c=COLORS["swot"], marker="D", lw=lw, ms=ms, label="SWOT", zorder=10
    )
    ax_main.plot(
        x,
        y_straw,
        c=COLORS["strawman"],
        marker="o",
        lw=lw,
        ms=ms,
        label="Strawman-ICR",
        zorder=5,
    )
    if not np.all(np.isnan(y_oneshot)):
        ax_main.plot(
            x,
            y_oneshot,
            c=COLORS["oneshot"],
            marker="x",
            lw=lw,
            ms=ms,
            label="One-shot",
            zorder=6,
        )
    ax_main.plot(
        x,
        y_ideal,
        c="#d5d6d5",
        marker="s",
        lw=lw,
        ls="--",
        ms=ms,
        label="Ideal",
        zorder=4,
    )

    for idx, (xv, yv, label) in enumerate(zip(x, y_swot, labels)):
        if pd.notna(yv) and label:
            ax_main.annotate(
                label,
                xy=(xv, yv),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color="#7f6000",
            )

    ax_main.set_xticks(x)
    ax_main.set_xticklabels(x_labels, fontsize=12)
    ax_main.set_xlabel("Message Size", fontsize=16)
    ax_main.set_ylabel("CCT (ms)", fontsize=16, fontweight="bold")
    if manual_ylim is not None:
        ax_main.set_ylim(0, manual_ylim)
    else:
        ymax = np.nanmax(np.concatenate([y_swot, y_straw]))
        ax_main.set_ylim(0, ymax * 1.35)
    ax_main.set_title(
        f"Performance Analysis (P={target_config['p']}, K={target_config['k']}, B={target_config['B']})",
        fontsize=18,
        pad=20,
    )
    ax_main.grid(True, alpha=0.3)
    ax_main.legend(loc="upper right", fontsize=12, framealpha=0.95, edgecolor="gray")

    g_start, g_end = gain_range
    g_end = min(g_end, len(x))
    if g_start < g_end:
        ax_gain = fig.add_axes([0.20, 0.60, 0.35, 0.22])
        x_g = x[g_start:g_end]
        y_g = y_gain[g_start:g_end]
        l_g = labels[g_start:g_end]
        max_g = max(np.nanmax(y_g), 10) if not np.all(np.isnan(y_g)) else 10
        min_g = min(np.nanmin(y_g), -5) if not np.all(np.isnan(y_g)) else -10
        y_top = max_g * 1.3
        y_bot = min_g * 1.2
        ax_gain.set_ylim(y_bot, y_top)
        ax_gain.axhspan(0, y_top, facecolor="#d5f5e3", alpha=0.6)
        ax_gain.axhspan(y_bot, 0, facecolor="#fadbd8", alpha=0.6)
        ax_gain.axhline(0, color="gray", linestyle="--", linewidth=1)
        ax_gain.plot(x_g, y_g, marker="o", color="#2c3e50", lw=1.5, ms=6)
        for i, val in enumerate(y_g):
            if pd.notna(val):
                color = "#1e8449" if val >= 0 else "#c0392b"
                offset = (y_top - y_bot) * 0.08
                pos_y = val + offset if val >= 0 else val - offset
                ax_gain.text(
                    x_g[i],
                    pos_y,
                    l_g[i],
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color=color,
                )
        ax_gain.set_xticks(x_g)
        ax_gain.set_xticklabels(x_labels[g_start:g_end], fontsize=9, linespacing=1.1)
        ax_gain.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
        ax_gain.set_title("SWOT Gain vs. Best Known", fontsize=11, fontweight="bold")

    z_start, z_end = zoom_range
    z_end = min(z_end, len(x))
    if z_start < z_end:
        ax_zoom = fig.add_axes([0.20, 0.25, 0.35, 0.22])
        x_z = x[z_start:z_end]
        ax_zoom.plot(x_z, y_swot[z_start:z_end], c=COLORS["swot"], marker="D", lw=2)
        ax_zoom.plot(
            x_z, y_straw[z_start:z_end], c=COLORS["strawman"], marker="o", lw=2
        )
        ax_zoom.plot(x_z, y_ideal[z_start:z_end], c="#d5d6d5", marker="s", lw=2)
        if not np.all(np.isnan(y_oneshot)):
            ax_zoom.plot(
                x_z, y_oneshot[z_start:z_end], c=COLORS["oneshot"], marker="x", lw=2
            )
        ax_zoom.set_xticks(x_z)
        ax_zoom.set_xticklabels(x_labels[z_start:z_end], fontsize=9, linespacing=1.1)
        ax_zoom.set_ylabel("CCT (ms)", fontsize=10)
        ax_zoom.set_title("Small Message Zoom", fontsize=11)
        ax_zoom.grid(True, alpha=0.3)
        y_conn = 0
        con1 = ConnectionPatch(
            xyA=(0, 0),
            xyB=(z_start, y_conn),
            coordsA="axes fraction",
            coordsB="data",
            axesA=ax_zoom,
            axesB=ax_main,
            color="gray",
            linestyle="--",
            alpha=0.5,
        )
        con2 = ConnectionPatch(
            xyA=(1, 0),
            xyB=(z_end - 1, y_conn),
            coordsA="axes fraction",
            coordsB="data",
            axesA=ax_zoom,
            axesB=ax_main,
            color="gray",
            linestyle="--",
            alpha=0.5,
        )
        fig.add_artist(con1)
        fig.add_artist(con2)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Figure written: {out_file}")


def plot_exp13_suite(
    df_ar: pd.DataFrame,
    df_a2a_9: pd.DataFrame,
    df_a2a_256: pd.DataFrame,
    output_dir: Path,
) -> None:
    df_ar = clamp_optimized_cct(df_ar)
    df_a2a_9 = clamp_optimized_cct(df_a2a_9)
    df_a2a_256 = clamp_optimized_cct(df_a2a_256)

    def resolve_config(
        df: pd.DataFrame, preferred_p: float, k: float, b: float
    ) -> dict[str, float]:
        exact = df[(df["p"] == preferred_p) & (df["k"] == k) & (np.isclose(df["B"], b))]
        if not exact.empty:
            return {"p": float(preferred_p), "k": float(k), "B": float(b)}
        fallback = df[(df["k"] == k) & (np.isclose(df["B"], b))]
        if fallback.empty:
            fallback = df
        if fallback.empty:
            raise ValueError("No available exp1.3 configuration rows in CSV.")
        row = fallback.iloc[0]
        print(
            "[WARN] Preferred exp1.3 config not found; fallback to "
            f"p={row['p']}, k={row['k']}, B={row['B']}"
        )
        return {"p": float(row["p"]), "k": float(row["k"]), "B": float(row["B"])}

    cfg_ar = {"p": 256.0, "k": 8.0, "B": 12.5}
    ar_algs = [
        "ar_having-doubling",
        "ar_recursive-doubling",
        "ar_ring",
        "ar_dbt",
        "ar_dbt_pipe",
    ]
    ar_plot_df = prepare_data_best(df_ar, cfg_ar, ar_algs)
    draw_comprehensive_plot(
        ar_plot_df,
        cfg_ar,
        output_dir / "exp1.3_ar.pdf",
        zoom_range=(0, 5),
        gain_range=(0, 13),
        manual_ylim=10,
    )

    a2a_algs = ["a2a_pairwise", "a2a_bruck"]
    cfg_a2a_9 = {"p": 9.0, "k": 8.0, "B": 12.5}
    cfg_a2a_256 = {"p": 256.0, "k": 8.0, "B": 12.5}
    cfg_a2a_9 = resolve_config(df_a2a_9, preferred_p=9.0, k=8.0, b=12.5)
    cfg_a2a_256 = resolve_config(df_a2a_256, preferred_p=256.0, k=8.0, b=12.5)

    a2a_9_df = prepare_data_best(df_a2a_9, cfg_a2a_9, a2a_algs)
    draw_comprehensive_plot(
        a2a_9_df,
        cfg_a2a_9,
        output_dir / "exp1.3_a2a_9.pdf",
        zoom_range=(2, 9),
        gain_range=(0, 13),
        manual_ylim=None,
    )

    a2a_256_df = prepare_data_best(df_a2a_256, cfg_a2a_256, a2a_algs)
    draw_comprehensive_plot(
        a2a_256_df,
        cfg_a2a_256,
        output_dir / "exp1.3_a2a_256.pdf",
        zoom_range=(0, 7),
        gain_range=(0, 13),
        manual_ylim=75,
    )


def plot_exp21_impact_k(df: pd.DataFrame, out_file: Path) -> None:
    df = clamp_optimized_cct(df)
    algs = ["ar_having-doubling", "a2a_pairwise", "a2a_bruck"]
    metric = "improvement_pct"

    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5), sharex="col")
    colors = plt.cm.tab20.colors

    for col, alg_name in enumerate(algs):
        ax = axes[col]
        title = ALGO_LABELS.get(alg_name, alg_name)
        subdf = df[
            (df["algorithm"] == alg_name) & (df["solver_time_limit"] == 120)
        ].copy()
        if subdf.empty:
            ax.set_title(f"{title}\n(no data)")
            ax.set_xlabel("Message Size")
            ax.set_xscale("log", base=2)
            ax.grid(alpha=0.3)
            continue

        pivot_df = subdf.pivot_table(
            values=["optimized_cct", "baseline_cct", "ideal_cct"],
            index=["message_mib", "k", "p"],
            aggfunc="first",
        ).reset_index()
        pivot_df[metric] = (
            (pivot_df["baseline_cct"] - pivot_df["optimized_cct"])
            / pivot_df["baseline_cct"]
        ) * 100

        msg_sizes = np.sort(pivot_df["message_mib"].unique())
        labels = [
            format_msg_size_label(float(size), multiline=True) for size in msg_sizes
        ]

        for i, k_val in enumerate(sorted(pivot_df["k"].dropna().unique())):
            grp = pivot_df[pivot_df["k"] == k_val].sort_values("message_mib")
            ax.plot(
                grp["message_mib"],
                grp[metric],
                marker="o",
                linestyle="-",
                color=colors[i % len(colors)],
                label=f"k={int(k_val)}",
            )

        ax.set_xlabel("Message Size")
        ax.set_xscale("log", base=2)
        ax.set_xticks(msg_sizes)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Improvement (%)")
        ax.grid(True, alpha=0.3)
        ax.set_title(title, fontsize=14)
        ax.legend(fontsize=10)

    plt.tight_layout()
    save_fig(out_file)


def plot_exp22_overhead(df: pd.DataFrame, out_file: Path) -> None:
    data = clamp_optimized_cct(df)
    data = data[np.isclose(data["B"], 25)].copy()
    if data.empty:
        raise ValueError("No exp2.2 data for B=25.")

    data["overhead_pct"] = (
        (data["baseline_cct"] - data["ideal_cct"]) / data["baseline_cct"]
    ) * 100
    unique_tr = sorted(data["T_reconf"].dropna().unique())
    unique_algs = ["ar_having-doubling", "a2a_pairwise", "a2a_bruck"]
    msg_sizes = np.sort(data["message_mib"].dropna().unique())
    x_labels = [
        format_msg_size_label(float(size), multiline=True) for size in msg_sizes
    ]
    alg_colors = {
        "ar_having-doubling": "#4f669f",
        "a2a_pairwise": "#c73934",
        "a2a_bruck": "#ecbc4a",
    }
    alg_labels = {
        "ar_having-doubling": "AllReduce",
        "a2a_pairwise": "A2A-Pair",
        "a2a_bruck": "A2A-Bruck",
    }

    fig, axes = plt.subplots(1, len(unique_tr), figsize=(6 * len(unique_tr), 5))
    if len(unique_tr) == 1:
        axes = [axes]

    for idx, tr_val in enumerate(unique_tr):
        ax = axes[idx]
        subdf = data[np.isclose(data["T_reconf"], tr_val)]
        for alg in unique_algs:
            alg_data = subdf[subdf["algorithm"] == alg].sort_values("message_mib")
            if alg_data.empty:
                continue
            ax.plot(
                alg_data["message_mib"],
                alg_data["overhead_pct"],
                marker="o",
                linestyle="--",
                color=alg_colors.get(alg, "gray"),
                label=alg_labels.get(alg, alg),
                linewidth=2,
                markersize=6,
            )
        ax.set_xscale("log", base=2)
        ax.set_xticks(msg_sizes)
        ax.set_xticklabels(x_labels)
        ax.set_xlabel("Message Size", fontsize=14)
        ax.set_ylabel("Reconfiguration Overhead (%)", fontsize=13)
        ax.grid(True, alpha=0.3)
        ax.set_title(f"T_reconf = {tr_val:g} ms", fontsize=14, fontweight="bold")
        ax.legend(loc="best", fontsize=12)

    plt.tight_layout()
    save_fig(out_file)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_exp11:
        exp11_df = clamp_optimized_cct(load_results(Path(args.exp11_csv)))
        plot_exp11_suite(exp11_df, output_dir)
        if args.write_summary:
            summary_path = output_dir / "exp1.1_summary.txt"
            summary_path.write_text(build_exp11_summary(exp11_df) + "\n")
            print(f"[OK] Summary written: {summary_path}")

    if not args.skip_exp12:
        exp12_hd_bruck = load_results(Path(args.exp12_hd_bruck_csv))
        exp12_pair = load_results(Path(args.exp12_pair_csv))
        plot_exp12_curve(
            exp12_hd_bruck, "ar_having-doubling", output_dir / "exp1.2_ar_hd.pdf"
        )
        plot_exp12_curve(
            exp12_hd_bruck, "a2a_bruck", output_dir / "exp1.2_a2a_bruck.pdf"
        )
        plot_exp12_curve(exp12_pair, "a2a_pairwise", output_dir / "exp1.2_a2a_pair.pdf")

    if not args.skip_exp13:
        exp13_ar = load_results(Path(args.exp13_ar_csv))
        exp13_a2a_9 = load_results(Path(args.exp13_a2a_9_csv))
        exp13_a2a_256 = load_results(Path(args.exp13_a2a_256_csv))
        plot_exp13_suite(exp13_ar, exp13_a2a_9, exp13_a2a_256, output_dir)

    if not args.skip_exp21:
        exp21_df = load_results(Path(args.exp21_csv))
        plot_exp21_impact_k(exp21_df, output_dir / "exp2.1_impact_k.pdf")

    if not args.skip_exp22:
        exp22_df = load_results(Path(args.exp22_csv))
        plot_exp22_overhead(exp22_df, output_dir / "exp2.2_impact_Treconf.pdf")


if __name__ == "__main__":
    main()
