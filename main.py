from config.instance_parser import get_parameters
from utils.scheduler_analysis import extract_results, plot_schedule
from paradigm.baseline import compute_baseline_schedule
from paradigm.one_shot import compute_oneshot_schedule
from paradigm.ideal import compute_ideal_time
from paradigm.warm_start import build_baseline_warm_start
import logging as log
import argparse
import toml
import os
import json
from datetime import datetime

def load_program_config(config_path='config/program.toml'):
    try:
        program_config = toml.load(config_path)
        return program_config
    except FileNotFoundError:
        log.warning(f"Configuration file {config_path} not found. Using default values.")
        return {
            "save_as_pdf": True,
            "debug_mode": 0,
            "show": False
        }

def write_metrics(metrics_path: str, payload: dict):
    directory = os.path.dirname(metrics_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(metrics_path, 'w') as metrics_file:
        json.dump(payload, metrics_file, indent=2)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run the scheduling program with custom parameters.")
    parser.add_argument('--config', type=str, default='config/instance.toml', help='Path to the instance configuration file.')
    parser.add_argument('--program-config', type=str, default='config/program.toml', help='Path to the program configuration file.')
    parser.add_argument('--run-id', type=str, default=None, help='Optional identifier for this run (stored in metrics).')
    parser.add_argument('--metrics-file', type=str, default=None, help='If provided, write aggregated results to this JSON file.')
    args = parser.parse_args()

    # Load program configuration
    program_config = load_program_config(args.program_config)
    show = program_config.get("show", False)
    save_as_pdf = program_config.get("save_as_pdf", True)
    debug_mode = program_config.get("debug_mode", 0)

    # Get parameter
    params = get_parameters(args.config)

    solver_gap = params.get('solver_gap')
    solver_time_limit = params.get('solver_time_limit')
    gap_str = f"{solver_gap:g}" if solver_gap is not None else "default"
    limit_str = f"{solver_time_limit}s" if solver_time_limit else "default"
    log.info(f"Solver options -> gap: {gap_str}, time_limit: {limit_str}")

    # Baseline schedule (used for warm start + reporting)
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
    warm_start_payload = build_baseline_warm_start(schedule_baseline, params, cct_baseline)
    warm_start_applied = True
    # NOTE: The baseline solution applied to warm start did not prove effective.
    # TODO: greedy policy for warm start
    
    # Build the model
    os.makedirs('figures', exist_ok=True)

    os.makedirs('solution', exist_ok=True)
    
    # .sol or .json
    solution_figure   =  f"figures/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    solution_file    =  f"solution/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.json"
    baseline_figure   =  f"figures/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    baseline_file    =  f"solution/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json"
    oneshot_figure    =  f"figures/oneshot_{params['algorithm']}_t_k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    oneshot_file     =  f"solution/oneshot_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json"
    
    # [Paradigm] Solver
    solver = params['solver']
    if solver == 'gurobi':
        from paradigm.model_gurobi import build_model
    elif solver == 'pulp' or solver == 'copt':
        from paradigm.model_pulp import build_model
    else:
        raise ValueError(f"Unsupported solver: {solver}")
    from paradigm.solver_wrapper import solve_model, get_solution_value, write_model, load_and_validate_solution

    # Build the model
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)

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
        warm_start_label=f"Applied baseline warm start (CCT={cct_baseline * 1000:.0f} μs)",
        solver_gap=solver_gap,
        solver_time_limit=solver_time_limit,
    )

    # Extract and display results
    schedule = extract_results(model, cct=cct, d=d, t_start=t_start, t_end=t_end, 
                             u=u, r=r, t_reconf_start=t_reconf_start, 
                             t_reconf_end=t_reconf_end, t_step_end=t_step_end, 
                             params=params)
    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=save_as_pdf, filename=solution_figure, show=show)
    write_model(model, solution_file, solver)

    # [Paradigm] Baseline (naive intra-collective reconfiguration)
    plot_schedule(schedule_baseline, params['k'], params['T_reconf'], save_as_pdf=save_as_pdf, filename=baseline_figure, show=show)
    write_model(model, baseline_file, solver)

    # [Paradigm] One-shot
    cct_oneshot, schedule_oneshot = compute_oneshot_schedule(params)
    if cct_oneshot is not None:
        plot_schedule(schedule_oneshot, params['k'], params['T_reconf'], save_as_pdf=save_as_pdf, filename=oneshot_figure, show=show)
        write_model(model, oneshot_file, solver)

    # [Paradigm] Ideal
    cct_ideal = compute_ideal_time(params)

    # Compare and analyze the results
    cct_optimized = get_solution_value(cct) - params['T_reconf']
    cct_baseline_adj = cct_baseline - params['T_reconf']
    log.info("\nComparison:")
    cct_oneshot_adj = None
    improvement_over_oneshot = None
    if cct_oneshot is not None:
        cct_oneshot_adj = cct_oneshot - params['T_reconf']
        log.info(f"One-shot CCT: {cct_oneshot_adj * 1000:.0f} μs")
    else:
        log.info("One-shot CCT: None")
        log.info("One-shot schedule is not feasible for current parameters")
    log.info(f"Baseline CCT:  {cct_baseline_adj * 1000:.0f} μs")
    log.info(f"Optimized CCT: {cct_optimized * 1000:.0f} μs")
    log.info(f"Ideal CCT:     {cct_ideal * 1000:.0f} μs")
    
    improvement_over_baseline = ((cct_baseline_adj - cct_optimized) / cct_baseline_adj) * 100 if cct_baseline_adj != 0 else 0
    log.info(f"Improvement over baseline: {improvement_over_baseline:.0f}%")
    
    if cct_oneshot is not None:
        improvement_over_oneshot = ((cct_oneshot_adj - cct_optimized) / cct_oneshot_adj) * 100 if cct_oneshot_adj != 0 else 0
        log.info(f"Improvement over one-shot: {improvement_over_oneshot:.0f}%")
    
    # DEBUG: debug_mode
    debug_solution_figure    =  f"figures/debug_solution_k={params['k']}_p={params['p']}.pdf"
    debug_solution_file      =  f"solution/debug_solution_k={params['k']}_p={params['p']}.json"
    if debug_mode == 1:
        model_debug, cct_debug, d_debug, t_start_debug, t_end_debug, u_debug, r_debug, t_reconf_start_debug, t_reconf_end_debug, t_step_end_debug = build_model(params, debug_model=True)
        model_debug, _ = solve_model(
            model_debug,
            solver,
            solver_gap=solver_gap,
            solver_time_limit=solver_time_limit,
        )
        schedule_debug = extract_results(model_debug, cct=cct_debug, d=d_debug, t_start=t_start_debug, t_end=t_end_debug, 
                                u=u_debug, r=r_debug, t_reconf_start=t_reconf_start_debug, 
                                t_reconf_end=t_reconf_end_debug, t_step_end=t_step_end_debug, 
                                params=params)
        plot_schedule(schedule_debug, params['k'], params['T_reconf'], save_as_pdf=save_as_pdf, filename=debug_solution_figure, show=show)
        write_model(model_debug, debug_solution_file, solver)
        log.info("Comparison:")
        cct_debug_optimized = cct_debug.X - params['T_reconf']
        log.info(f"Optimized CCT with debug model: {(cct_debug_optimized) * 1000:.0f} μs")
        log.info(f"Baseline CCT: {cct_baseline * 1000:.0f} μs")
        improvement = ((cct_baseline - cct_debug_optimized) / cct_baseline) * 100 if cct_baseline != 0 else 0
        log.info(f"Improvement: {improvement:.0f}%")
        load_and_validate_solution(params, debug_solution_file, if_debug_model=False, solver=solver)
        load_and_validate_solution(params, solution_file, if_debug_model=True, solver=solver)

    elif debug_mode == 2:
        compare_file = "solution/modified_solution_k=2_p=8.json"
        load_and_validate_solution(params, compare_file, if_debug_model=True, solver=solver)

    if args.metrics_file:
        metrics_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_id": args.run_id,
            "config_file": args.config,
            "program_config": args.program_config,
            "solver": solver,
            "status": "success",
            "figures": {
                "solution": solution_figure,
                "baseline": baseline_figure,
                "oneshot": oneshot_figure if cct_oneshot is not None else None,
                "warm_start_applied": warm_start_applied,
                "debug": debug_solution_figure if debug_mode == 1 else None
            },
            "solutions": {
                "solution": solution_file,
                "baseline": baseline_file,
                "oneshot": oneshot_file if cct_oneshot is not None else None,
                "debug": debug_solution_file if debug_mode == 1 else None
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
        write_metrics(args.metrics_file, metrics_payload)

if __name__ == "__main__":
    log.basicConfig(level=log.INFO, format='%(message)s')
    main()
