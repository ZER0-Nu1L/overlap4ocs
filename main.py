"""
SWOT Scheduler - Main entry point.

This module orchestrates the scheduling workflow by delegating to specialized
functions in the orchestrator module.
"""

import argparse
import logging as log
import os

import toml

from config.instance_parser import get_parameters
from orchestrator import (
    build_and_solve_model,
    build_metrics_payload,
    compute_reference_schedules,
    extract_and_validate_solution,
    generate_output_paths,
    log_results,
    save_solutions,
    select_warm_start,
    write_metrics,
)
from paradigm.solver_wrapper import load_and_validate_solution
from utils.scheduler_analysis import plot_schedule


def load_program_config(config_path="config/program.toml"):
    """Load program configuration from TOML file."""
    try:
        program_config = toml.load(config_path)
        return program_config
    except FileNotFoundError:
        log.warning(
            f"Configuration file {config_path} not found. Using default values."
        )
        return {
            "save_as_pdf": True,
            "debug_mode": 0,
            "show": False,
            "figure_format": "pdf",
            "figure_width": 12,
            "figure_height": 3.8,
            "figure_dpi": 100,
        }


def run_debug_mode(
    params, solver, solver_gap, solver_time_limit, save_as_pdf, show, debug_mode
):
    """
    Run debug mode workflows.

    Args:
        params: Problem parameters
        solver: Solver name
        solver_gap: MIP gap tolerance
        solver_time_limit: Time limit
        save_as_pdf: Whether to save PDFs
        show: Whether to show plots
        debug_mode: Debug mode (1 or 2)

    Returns:
        dict: Debug output paths (for metrics)
    """
    from paradigm.model_gurobi import build_model
    from paradigm.solver_wrapper import get_solution_value, solve_model, write_model
    from utils.scheduler_analysis import extract_results, plot_schedule

    debug_solution_figure = (
        f"figures/debug_solution_k={params['k']}_p={params['p']}.pdf"
    )
    debug_solution_file = (
        f"solution/debug_solution_k={params['k']}_p={params['p']}.json"
    )

    if debug_mode == 1:
        # Build and solve debug model
        (
            model_debug,
            cct_debug,
            d_debug,
            t_start_debug,
            t_end_debug,
            u_debug,
            r_debug,
            t_reconf_start_debug,
            t_reconf_end_debug,
            t_step_end_debug,
        ) = build_model(params, debug_model=True)
        model_debug, _ = solve_model(
            model_debug,
            solver,
            solver_gap=solver_gap,
            solver_time_limit=solver_time_limit,
        )
        schedule_debug = extract_results(
            model_debug,
            cct=cct_debug,
            d=d_debug,
            t_start=t_start_debug,
            t_end=t_end_debug,
            u=u_debug,
            r=r_debug,
            t_reconf_start=t_reconf_start_debug,
            t_reconf_end=t_reconf_end_debug,
            t_step_end=t_step_end_debug,
            params=params,
        )
        plot_schedule(
            schedule_debug,
            params["k"],
            params["T_reconf"],
            save_as_pdf=save_as_pdf,
            filename=debug_solution_figure,
            show=show,
        )
        write_model(model_debug, debug_solution_file, solver)

        cct_debug_optimized = get_solution_value(cct_debug) - params["T_reconf"]
        log.info("Comparison:")
        log.info(
            f"Optimized CCT with debug model: {(cct_debug_optimized) * 1000:.0f} μs"
        )

        # Validate both solutions
        load_and_validate_solution(
            params, debug_solution_file, if_debug_model=False, solver=solver
        )

    elif debug_mode == 2:
        # Load and validate external solution
        compare_file = "solution/modified_solution_k=2_p=8.json"
        load_and_validate_solution(
            params, compare_file, if_debug_model=True, solver=solver
        )

    return {
        "figure": debug_solution_figure if debug_mode == 1 else None,
        "file": debug_solution_file if debug_mode == 1 else None,
    }


def main():
    """Main entry point for SWOT scheduler."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Run the scheduling program with custom parameters."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/instance.toml",
        help="Path to the instance configuration file.",
    )
    parser.add_argument(
        "--program-config",
        type=str,
        default="config/program.toml",
        help="Path to the program configuration file.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional identifier for this run (stored in metrics).",
    )
    parser.add_argument(
        "--metrics-file",
        type=str,
        default=None,
        help="If provided, write aggregated results to this JSON file.",
    )
    args = parser.parse_args()

    # Load configurations
    params = get_parameters(args.config)
    program_config = load_program_config(args.program_config)
    show = program_config.get("show", False)
    save_as_pdf = program_config.get("save_as_pdf", True)
    debug_mode = program_config.get("debug_mode", 0)
    figure_format = (
        str(program_config.get("figure_format", "pdf")).strip().lower().lstrip(".")
    )
    figure_width = float(program_config.get("figure_width", 12))
    figure_height = float(program_config.get("figure_height", 3.8))
    figure_dpi = int(program_config.get("figure_dpi", 100))
    figure_style = {
        "figsize": (figure_width, figure_height),
        "dpi": figure_dpi,
    }

    # Create output directories
    os.makedirs("figures", exist_ok=True)
    os.makedirs("solution", exist_ok=True)

    # Generate output paths
    output_paths = generate_output_paths(params, figure_ext=figure_format)
    if program_config.get("optimized_figure_filename"):
        output_paths["solution_figure"] = program_config["optimized_figure_filename"]
    if program_config.get("baseline_figure_filename"):
        output_paths["baseline_figure"] = program_config["baseline_figure_filename"]
    if program_config.get("oneshot_figure_filename"):
        output_paths["oneshot_figure"] = program_config["oneshot_figure_filename"]

    # Compute reference schedules (baseline, one-shot, ideal)
    cct_baseline, schedule_baseline, cct_oneshot, schedule_oneshot, cct_ideal = (
        compute_reference_schedules(
            params,
            output_paths,
            save_as_pdf=save_as_pdf,
            show=show,
            figure_style=figure_style,
        )
    )

    # Select best warm start
    solver_gap = params.get("solver_gap")
    solver_time_limit = params.get("solver_time_limit")
    gap_str = f"{solver_gap:g}" if solver_gap is not None else "default"
    limit_str = f"{solver_time_limit}s" if solver_time_limit else "default"
    log.info(f"Solver options -> gap: {gap_str}, time_limit: {limit_str}")

    (
        warm_start_payload,
        warm_start_label,
        warm_start_choice,
        warm_start_cct,
        warm_start_schedule,
    ) = select_warm_start(
        cct_baseline, schedule_baseline, cct_oneshot, schedule_oneshot, params
    )

    # Build and solve MILP model
    (
        model,
        cct,
        d,
        t_start,
        t_end,
        u,
        r,
        t_reconf_start,
        t_reconf_end,
        t_step_end,
        warm_start_applied,
    ) = build_and_solve_model(
        params, warm_start_payload, warm_start_label, solver_gap, solver_time_limit
    )

    # Extract and validate solution
    warm_start_cct_adj = None
    if warm_start_cct is not None:
        warm_start_cct_adj = warm_start_cct - params["T_reconf"]

    schedule, cct_optimized, fallback_used = extract_and_validate_solution(
        model,
        cct,
        d,
        t_start,
        t_end,
        u,
        r,
        t_reconf_start,
        t_reconf_end,
        t_step_end,
        params,
        warm_start_cct_adj,
        warm_start_schedule,
    )

    # Plot and save optimized solution
    plot_schedule(
        schedule,
        params["k"],
        params["T_reconf"],
        save_as_pdf=save_as_pdf,
        filename=output_paths["solution_figure"],
        show=show,
        title="Optimized Transmission and Reconfiguration Schedule",
        **figure_style,
    )
    save_solutions(
        schedule,
        model,
        params["solver"],
        fallback_used,
        output_paths,
        schedule_baseline,
        cct_oneshot,
        schedule_oneshot,
    )

    # Log comparison results
    (
        improvement_over_baseline,
        improvement_over_oneshot,
        cct_baseline_adj,
        cct_oneshot_adj,
    ) = log_results(cct_baseline, cct_oneshot, cct_optimized, params)

    # Debug mode
    debug_outputs = None
    if debug_mode > 0:
        debug_outputs = run_debug_mode(
            params,
            params["solver"],
            solver_gap,
            solver_time_limit,
            save_as_pdf,
            show,
            debug_mode,
        )
        if debug_mode == 1:
            # Also validate the main solution against debug model
            load_and_validate_solution(
                params,
                output_paths["solution_file"],
                if_debug_model=True,
                solver=params["solver"],
            )

    # Write metrics if requested
    if args.metrics_file:
        metrics_payload = build_metrics_payload(
            args,
            params,
            params["solver"],
            output_paths,
            warm_start_applied,
            warm_start_choice,
            warm_start_cct,
            fallback_used,
            cct_optimized,
            cct_baseline_adj,
            cct_oneshot,
            cct_oneshot_adj,
            cct_ideal,
            improvement_over_baseline,
            improvement_over_oneshot,
            solver_gap,
            solver_time_limit,
            debug_mode,
        )

        # Add debug outputs if available
        if debug_outputs:
            metrics_payload["figures"]["debug"] = debug_outputs.get("figure")
            metrics_payload["solutions"]["debug"] = debug_outputs.get("file")

        write_metrics(args.metrics_file, metrics_payload)


if __name__ == "__main__":
    log.basicConfig(level=log.INFO, format="%(message)s")
    main()
