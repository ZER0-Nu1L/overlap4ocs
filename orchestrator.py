"""
Orchestrator module for SWOT scheduler.

This module breaks down the monolithic main() function into smaller,
testable components with clear responsibilities.
"""
import os
import json
from datetime import datetime
import logging as log

from config.instance_parser import get_parameters
from utils.scheduler_analysis import extract_results, plot_schedule
from paradigm.baseline import compute_baseline_schedule
from paradigm.one_shot import compute_oneshot_schedule
from paradigm.ideal import compute_ideal_time
from paradigm.warm_start import build_baseline_warm_start
from paradigm.solver_wrapper import solve_model, get_solution_value, write_model


def generate_output_paths(params):
    """
    Generate standardized output file paths for figures and solutions.

    Args:
        params: Dictionary of problem parameters

    Returns:
        dict: Dictionary containing all output paths
    """
    alg = params['algorithm']
    k = params['k']
    p = params['p']
    m = params['m']

    return {
        'solution_figure': f"figures/solution_{alg}_break_k={k}_p={p}_m={m}.pdf",
        'solution_file': f"solution/solution_{alg}_break_k={k}_p={p}_m={m}.json",
        'baseline_figure': f"figures/baseline_{alg}__k={k}_p={p}_m={m}.pdf",
        'baseline_file': f"solution/baseline_{alg}__k={k}_p={p}_m={m}.json",
        'oneshot_figure': f"figures/oneshot_{alg}_t_k={k}_p={p}_m={m}.pdf",
        'oneshot_file': f"solution/oneshot_{alg}__k={k}_p={p}_m={m}.json",
    }


def compute_reference_schedules(params, output_paths, save_as_pdf=True, show=False):
    """
    Compute baseline, one-shot, and ideal reference schedules.

    Args:
        params: Problem parameters
        output_paths: Dictionary of output file paths
        save_as_pdf: Whether to save plots as PDF
        show: Whether to display plots interactively

    Returns:
        tuple: (cct_baseline, schedule_baseline, cct_oneshot, schedule_oneshot, cct_ideal)
    """
    # Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
    plot_schedule(
        schedule_baseline, params['k'], params['T_reconf'],
        save_as_pdf=save_as_pdf, filename=output_paths['baseline_figure'], show=show
    )

    # One-shot
    cct_oneshot, schedule_oneshot = compute_oneshot_schedule(params)
    if cct_oneshot is not None:
        plot_schedule(
            schedule_oneshot, params['k'], params['T_reconf'],
            save_as_pdf=save_as_pdf, filename=output_paths['oneshot_figure'], show=show
        )

    # Ideal
    cct_ideal = compute_ideal_time(params)

    return cct_baseline, schedule_baseline, cct_oneshot, schedule_oneshot, cct_ideal


def select_warm_start(cct_baseline, schedule_baseline, cct_oneshot, schedule_oneshot, params):
    """
    Select the best warm start between baseline and one-shot schedules.

    Args:
        cct_baseline: Baseline CCT
        schedule_baseline: Baseline schedule
        cct_oneshot: One-shot CCT (or None if infeasible)
        schedule_oneshot: One-shot schedule (or None if infeasible)
        params: Problem parameters

    Returns:
        tuple: (warm_start_payload, warm_start_label, warm_start_choice, warm_start_cct, warm_start_schedule)
    """
    warm_start_choice = "baseline"
    warm_start_cct = cct_baseline
    warm_start_schedule = schedule_baseline

    # Check if one-shot is better
    if cct_oneshot is not None and schedule_oneshot:
        if warm_start_cct is None or cct_oneshot < warm_start_cct:
            warm_start_choice = "one-shot"
            warm_start_cct = cct_oneshot
            warm_start_schedule = schedule_oneshot

    # Build warm start payload
    warm_start_payload = None
    warm_start_label = None
    if warm_start_schedule and warm_start_cct is not None:
        warm_start_payload = build_baseline_warm_start(warm_start_schedule, params, warm_start_cct)
        if warm_start_payload:
            warm_start_label = f"Applied {warm_start_choice} warm start (CCT={warm_start_cct * 1000:.0f} μs)"

    return warm_start_payload, warm_start_label, warm_start_choice, warm_start_cct, warm_start_schedule


def build_and_solve_model(params, warm_start_payload, warm_start_label, solver_gap, solver_time_limit):
    """
    Build the MILP model and solve it.

    Args:
        params: Problem parameters
        warm_start_payload: Warm start data (or None)
        warm_start_label: Label for logging warm start
        solver_gap: MIP gap tolerance
        solver_time_limit: Time limit in seconds

    Returns:
        tuple: (model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, warm_start_applied)
    """
    solver = params['solver']

    # Import appropriate model builder
    if solver == 'gurobi':
        from paradigm.model_gurobi import build_model
    elif solver == 'pulp' or solver == 'copt':
        from paradigm.model_pulp import build_model
    else:
        raise ValueError(f"Unsupported solver: {solver}")

    # Build model
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)

    # Solve model
    model, warm_start_applied = solve_model(
        model,
        solver,
        warm_start_payload=warm_start_payload,
        warm_start_variables={
            'cct': cct,
            'd': d,
            't_start': t_start,
            't_end': t_end,
            'u': u,
            'r': r,
            't_reconf_start': t_reconf_start,
            't_reconf_end': t_reconf_end,
            't_step_end': t_step_end,
        },
        warm_start_label=warm_start_label,
        solver_gap=solver_gap,
        solver_time_limit=solver_time_limit,
    )

    return model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, warm_start_applied


def extract_and_validate_solution(
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end,
    params, warm_start_cct, warm_start_schedule
):
    """
    Extract solution from model and validate against warm start.

    Args:
        model: Solved MILP model
        cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end: Model variables
        params: Problem parameters
        warm_start_cct: Warm start CCT (adjusted)
        warm_start_schedule: Warm start schedule

    Returns:
        tuple: (schedule, cct_optimized, fallback_used)
    """
    # Extract results
    schedule = extract_results(
        model, cct=cct, d=d, t_start=t_start, t_end=t_end,
        u=u, r=r, t_reconf_start=t_reconf_start,
        t_reconf_end=t_reconf_end, t_step_end=t_step_end,
        params=params
    )

    # Validate against warm start
    cct_optimized = get_solution_value(cct) - params['T_reconf']
    fallback_used = False

    if warm_start_cct is not None and cct_optimized > warm_start_cct + 1e-9:
        log.warning(
            "Final solution worse than warm start (%.6g > %.6g); falling back to warm-start schedule",
            cct_optimized, warm_start_cct
        )
        schedule = warm_start_schedule
        cct_optimized = warm_start_cct
        fallback_used = True

    return schedule, cct_optimized, fallback_used


def save_solutions(
    schedule, model, solver, fallback_used, output_paths,
    schedule_baseline, cct_oneshot, schedule_oneshot
):
    """
    Save all solution files.

    Args:
        schedule: Optimized schedule
        model: Solved model
        solver: Solver name
        fallback_used: Whether warm start fallback was used
        output_paths: Dictionary of output file paths
        schedule_baseline: Baseline schedule
        cct_oneshot: One-shot CCT
        schedule_oneshot: One-shot schedule
    """
    # Save optimized solution
    if fallback_used:
        with open(output_paths['solution_file'], 'w') as sol_fp:
            json.dump(schedule, sol_fp, indent=2)
    else:
        write_model(model, output_paths['solution_file'], solver)

    # Save baseline solution
    with open(output_paths['baseline_file'], 'w') as baseline_fp:
        json.dump(schedule_baseline, baseline_fp, indent=2)

    # Save one-shot solution if it exists
    if cct_oneshot is not None and schedule_oneshot:
        with open(output_paths['oneshot_file'], 'w') as oneshot_fp:
            json.dump(schedule_oneshot, oneshot_fp, indent=2)


def log_results(cct_baseline, cct_oneshot, cct_optimized, params):
    """
    Log comparison results.

    Args:
        cct_baseline: Baseline CCT
        cct_oneshot: One-shot CCT (or None)
        cct_optimized: Optimized CCT
        params: Problem parameters

    Returns:
        tuple: (improvement_over_baseline, improvement_over_oneshot)
    """
    cct_baseline_adj = cct_baseline - params['T_reconf']
    cct_oneshot_adj = None
    improvement_over_oneshot = None

    log.info("\nComparison:")
    if cct_oneshot is not None:
        cct_oneshot_adj = cct_oneshot - params['T_reconf']
        log.info(f"One-shot CCT: {cct_oneshot_adj * 1000:.0f} μs")
        improvement_over_oneshot = ((cct_oneshot_adj - cct_optimized) / cct_oneshot_adj) * 100 if cct_oneshot_adj != 0 else 0
        log.info(f"Improvement over one-shot: {improvement_over_oneshot:.0f}%")
    else:
        log.info("One-shot CCT: None")
        log.info("One-shot schedule is not feasible for current parameters")

    log.info(f"Baseline CCT:  {cct_baseline_adj * 1000:.0f} μs")
    log.info(f"Optimized CCT: {cct_optimized * 1000:.0f} μs")
    improvement_over_baseline = ((cct_baseline_adj - cct_optimized) / cct_baseline_adj) * 100 if cct_baseline_adj != 0 else 0
    log.info(f"Improvement over baseline: {improvement_over_baseline:.0f}%")

    return improvement_over_baseline, improvement_over_oneshot, cct_baseline_adj, cct_oneshot_adj


def write_metrics(metrics_path, payload):
    """Write metrics to JSON file."""
    directory = os.path.dirname(metrics_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(metrics_path, 'w') as metrics_file:
        json.dump(payload, metrics_file, indent=2)


def build_metrics_payload(
    args, params, solver, output_paths, warm_start_applied, warm_start_choice,
    warm_start_cct, fallback_used, cct_optimized, cct_baseline_adj,
    cct_oneshot, cct_oneshot_adj, cct_ideal, improvement_over_baseline,
    improvement_over_oneshot, solver_gap, solver_time_limit, debug_mode
):
    """Build metrics payload for output."""
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "run_id": args.run_id,
        "config_file": args.config,
        "program_config": args.program_config,
        "solver": solver,
        "status": "success",
        "figures": {
            "solution": output_paths['solution_figure'],
            "baseline": output_paths['baseline_figure'],
            "oneshot": output_paths['oneshot_figure'] if cct_oneshot is not None else None,
            "warm_start_applied": warm_start_applied,
            "warm_start_source": warm_start_choice,
            "warm_start_cct": warm_start_cct,
            "warm_start_fallback_used": fallback_used,
            "debug": None  # Filled in if debug_mode == 1
        },
        "solutions": {
            "solution": output_paths['solution_file'],
            "baseline": output_paths['baseline_file'],
            "oneshot": output_paths['oneshot_file'] if cct_oneshot is not None else None,
            "debug": None  # Filled in if debug_mode == 1
        },
        "cct": {
            "optimized": cct_optimized,
            "baseline": cct_baseline_adj,
            "oneshot": cct_oneshot_adj if cct_oneshot is not None else None,
            "ideal": cct_ideal
        },
        "improvement_percent": {
            "over_baseline": improvement_over_baseline,
            "over_oneshot": improvement_over_oneshot if cct_oneshot is not None else None
        },
        "params": params,
        "solver_options": {
            "gap": solver_gap,
            "time_limit": solver_time_limit,
        },
        "notes": {
            "debug_mode": debug_mode
        }
    }
