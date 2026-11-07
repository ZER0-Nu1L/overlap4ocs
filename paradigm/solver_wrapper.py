import os
import json
import logging as log
from utils import check_platform
from paradigm.warm_start import apply_warm_start

def get_solution_value(var):
    """
    Uniformly obtain optimal solutions for variables, 
    whether Gurobi or PuLP or COPT.
    """
    return var.X if hasattr(var, 'X') else var.varValue

def write_model(model, filename, solver):
    """
    Write the solution of the model to a file.
    For Gurobi, directly call model.write;
    For PuLP/COPT, convert all variables and their solutions to JSON format and write to a file.
    """
    if solver == 'gurobi':
        model.write(filename)
    elif solver in ('pulp', 'copt', 'pulp_gurobi'):
        solution = {}
        for var in model.variables():
            solution[var.name] = var.varValue
        with open(filename, 'w') as f:
            json.dump(solution, f, indent=4)
    else:
        raise ValueError(f"Unsupported solver: {solver}")

def solve_model(
    model,
    solver,
    warm_start_payload=None,
    warm_start_variables=None,
    warm_start_label: str | None = None,
    solver_gap: float | None = None,
    solver_time_limit: float | None = None,
    solver_threads: int | None = None,
    solver_seed: int | None = None,
    solver_artifact_dir: str | None = None,
):
    """Solve the model and optionally apply a warm start before optimization."""
    warm_start_applied = False
    if warm_start_payload and warm_start_variables:
        warm_start_applied = apply_warm_start(solver, warm_start_variables, warm_start_payload)
        if warm_start_applied and warm_start_label:
            log.info(warm_start_label)

    if solver == 'gurobi':
        from gurobipy import GRB
        if solver_threads is not None:
            model.setParam('Threads', solver_threads)
        if solver_seed is not None:
            model.setParam('Seed', solver_seed)
        if solver_gap is not None:
            model.setParam('MIPGap', float(solver_gap))
        if solver_time_limit and solver_time_limit > 0:
            model.setParam('TimeLimit', float(solver_time_limit))

        if warm_start_applied:
            try:
                # Check if warm start is feasible via relaxation; >0 objective means violations present
                relax = model.feasRelaxS(0, False, False, True)
                relax.optimize()
                if relax.Status == GRB.OPTIMAL and relax.ObjVal > 1e-6:
                    log.warning("Warm start appears infeasible; relaxation objective=%.6g", relax.ObjVal)
            except Exception as exc:  # noqa: BLE001
                log.warning("Warm start feasibility check skipped (error: %s)", exc)
        model.optimize()
        status = model.status
        if status == GRB.TIME_LIMIT:
            if model.SolCount > 0:
                incumbent = getattr(model, 'ObjVal', None)
                log.warning(
                    "Gurobi hit TimeLimit but has %d incumbent solution(s); best objective=%s",
                    model.SolCount,
                    incumbent,
                )
            else:
                raise RuntimeError("Gurobi reached TimeLimit without a feasible solution")
        elif status == GRB.INFEASIBLE:
            raise RuntimeError("Gurobi reported model as infeasible")
        elif status == GRB.UNBOUNDED:
            raise RuntimeError("Gurobi reported model as unbounded")
        elif status == GRB.INF_OR_UNBD:
            raise RuntimeError("Gurobi reported model as infeasible or unbounded")
        elif status not in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
            if model.SolCount > 0:
                log.warning(
                    "Gurobi ended with status %s but has incumbent solution; proceeding with incumbent",
                    status,
                )
            else:
                raise RuntimeError(f"Gurobi terminated with status {status} and no solution")
    elif solver == 'pulp':
        import pulp
        import multiprocessing
        num_threads = solver_threads or multiprocessing.cpu_count()
        time_limit = solver_time_limit if (solver_time_limit and solver_time_limit > 0) else None
        solver_kwargs = {
            'msg': True,
            'threads': num_threads,
        }
        if solver_seed is not None:
            solver_kwargs['options'] = [f'randomSeed {solver_seed}', f'randomCbcSeed {solver_seed}']
        if solver_artifact_dir is None:
            from uuid import uuid4
            solver_artifact_dir = os.path.join('logs', 'solver-' + uuid4().hex)
        if solver_artifact_dir:
            from pathlib import Path
            artifact_dir = Path(solver_artifact_dir).resolve()
            artifact_dir.mkdir(parents=True, exist_ok=True)
            model.name = str(artifact_dir / 'cbc')
            solver_kwargs.update(logPath=str(artifact_dir / 'cbc.log'), keepFiles=True)
        if solver_gap is not None:
            solver_kwargs['gapRel'] = solver_gap
        if time_limit is not None:
            solver_kwargs['timeLimit'] = time_limit

        # For Arm-based Mac platforms.
        # Reference: https://github.com/tyler-griggs/melange-release/blob/main/melange/solver.py
        # Allow custom CBC path via environment variable (defaults to Homebrew path on ARM Mac)
        if check_platform.is_arm_mac():
            cbc_path = os.getenv('CBC_PATH', '/opt/homebrew/opt/cbc/bin/cbc')
            pulp_solver = pulp.getSolver('COIN_CMD', path=cbc_path, **solver_kwargs)
        else:
            pulp_solver = pulp.PULP_CBC_CMD(**solver_kwargs)

        # Preserve the previous CBC no-MIP-start behavior explicitly: setting
        # PuLP variable initials alone did not submit a CBC MIP start.
        model.solve(pulp_solver)
        if solver_artifact_dir:
            from utils.solver_evidence import parse_cbc_log
            model.solver_evidence = parse_cbc_log(
                (artifact_dir / 'cbc.log').read_text(),
                pulp.value(model.objective), model.sol_status,
            )
            model.solver_evidence['warm_start_submitted'] = False
        warm_start_applied = False
    elif solver == 'pulp_gurobi':
        import pulp
        import multiprocessing

        num_threads = solver_threads or multiprocessing.cpu_count()
        solver_kwargs = {
            'msg': True,
            'warmStart': bool(warm_start_applied),
        }
        if solver_time_limit and solver_time_limit > 0:
            solver_kwargs['timeLimit'] = float(solver_time_limit)

        gurobi_options = []
        if solver_gap is not None:
            gurobi_options.append(('MIPGap', float(solver_gap)))
        if num_threads:
            gurobi_options.append(('Threads', num_threads))
        if gurobi_options:
            solver_kwargs['options'] = gurobi_options

        gurobi_cmd_path = os.environ.get('GUROBI_CMD_PATH')
        if gurobi_cmd_path:
            solver_kwargs['path'] = gurobi_cmd_path

        pulp_solver = pulp.GUROBI_CMD(**solver_kwargs)
        model.solve(pulp_solver)
    elif solver == 'copt':
        from pulp import COPT
        copt_solver = COPT()
        if solver_gap is not None or (solver_time_limit and solver_time_limit > 0):
            log.warning("solver_gap/solver_time_limit are not currently applied for COPT solver")
        model.solve(copt_solver)
    else:
        raise ValueError(f"Unsupported solver: {solver}")
    return model, warm_start_applied

# TODO: test
def load_solution(params, filename, solver):
    """
    Load solution file and convert to unified data structure.
    For PuLP JSON format, variable names follow the pattern "varname_index"
    Examples: "d_1_1", "t_start_1_1", "CCT", "t_step_end_1", etc.
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Solution file {filename} not found.")
    with open(filename, 'r') as f:
        sol = json.load(f)
    if "CCT" not in sol:
        raise ValueError("Solution file does not contain 'CCT' variable.")
    cct = sol["CCT"]
    d = {}
    t_start = {}
    t_end = {}
    u = {}
    r = {}
    t_reconf_start = {}
    t_reconf_end = {}
    t_step_end = {}
    num_steps = params["num_steps"]
    k = params["k"]
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            d[(i, j)] = sol[f"d_{i}_{j}"]
            t_start[(i, j)] = sol[f"t_start_{i}_{j}"]
            t_end[(i, j)] = sol[f"t_end_{i}_{j}"]
            u[(i, j)] = sol[f"u_{i}_{j}"]
            r[(i, j)] = sol[f"r_{i}_{j}"]
            t_reconf_start[(i, j)] = sol[f"t_reconf_start_{i}_{j}"]
            t_reconf_end[(i, j)] = sol[f"t_reconf_end_{i}_{j}"]
        t_step_end[i] = sol[f"t_step_end_{i}"]
    return cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end

# TODO: test
def validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, debug_model=False):
    """Check raw saved timings using the independent physical validator."""
    from utils.fig11_validation import validate_schedule
    schedule = []
    for i in range(1, params['num_steps'] + 1):
        for j in range(1, params['k'] + 1):
            key = (i, j)
            schedule.append(dict(step=i, ocs=j, d=d[key], used=u[key], reconf=r[key],
                t_start=t_start[key], t_end=t_end[key], t_reconf_start=t_reconf_start[key],
                t_reconf_end=t_reconf_end[key]))
    report = validate_schedule(params, schedule, cct, t_step_end)
    if not report['valid']:
        log.error("Invalid schedule: %s", report['errors'])
    return report['valid']


def load_and_validate_solution(params, filename, if_debug_model=False, solver='pulp'):
    """
    Load solution file, validate feasibility, and output validation results
    """
    cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = load_solution(params, filename, solver)
    valid = validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, if_debug_model)
    model_mode = "debug" if if_debug_model else "normal"
    log.info(f"Solution is {'feasible' if valid else 'infeasible'} in {model_mode} model\n")
    return valid