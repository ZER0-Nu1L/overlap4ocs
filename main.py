from config.instance_parser import get_parameters
from utils.scheduler_analysis import extract_results, plot_schedule
from paradigm.baseline import compute_baseline_schedule
from paradigm.one_shot import compute_oneshot_schedule
from paradigm.ideal import compute_ideal_time
import logging as log
import argparse
import toml

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

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run the scheduling program with custom parameters.")
    parser.add_argument('--config', type=str, default='config/instance.toml', help='Path to the instance configuration file.')
    args = parser.parse_args()

    # Load program configuration
    program_config = load_program_config('config/program.toml')
    show = program_config.get("show", False)
    save_as_pdf = program_config.get("save_as_pdf", True)
    debug_mode = program_config.get("debug_mode", 0)

    # Get parameter
    params = get_parameters(args.config)

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
    model = solve_model(model, solver)

    # Extract and display results
    schedule = extract_results(model, cct=cct, d=d, t_start=t_start, t_end=t_end, 
                             u=u, r=r, t_reconf_start=t_reconf_start, 
                             t_reconf_end=t_reconf_end, t_step_end=t_step_end, 
                             params=params)
    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=save_as_pdf, filename=solution_figure, show=show)
    write_model(model, solution_file, solver)

    # [Paradigm] Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
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
        model_debug = solve_model(model_debug, solver)
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

if __name__ == "__main__":
    log.basicConfig(level=log.INFO, format='%(message)s')
    main()
