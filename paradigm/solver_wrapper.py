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
):
    """Solve the model and optionally apply a warm start before optimization."""
    warm_start_applied = False
    if warm_start_payload and warm_start_variables:
        warm_start_applied = apply_warm_start(solver, warm_start_variables, warm_start_payload)
        if warm_start_applied and warm_start_label:
            log.info(warm_start_label)

    if solver == 'gurobi':
        from gurobipy import GRB
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
        num_threads = multiprocessing.cpu_count()
        time_limit = solver_time_limit if (solver_time_limit and solver_time_limit > 0) else None
        solver_kwargs = {
            'msg': True,
            'threads': num_threads,
        }
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

        model.solve(pulp_solver)        
    elif solver == 'pulp_gurobi':
        import pulp
        import multiprocessing

        num_threads = multiprocessing.cpu_count()
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
            d[(i, j)] = sol.get(f"d_{i}_{j}", 0)
            t_start[(i, j)] = sol.get(f"t_start_{i}_{j}", 0)
            t_end[(i, j)] = sol.get(f"t_end_{i}_{j}", 0)
            u[(i, j)] = sol.get(f"u_{i}_{j}", 0)
            r[(i, j)] = sol.get(f"r_{i}_{j}", 0)
            t_reconf_start[(i, j)] = sol.get(f"t_reconf_start_{i}_{j}", 0)
            t_reconf_end[(i, j)] = sol.get(f"t_reconf_end_{i}_{j}", 0)
        t_step_end[i] = sol.get(f"t_step_end_{i}", 0)
    return cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end

# TODO: test
def validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, debug_model=False):
    """
    Validate that the solution satisfies all constraints.
    Consistent with _validate_solution in model_gurobi.py
    """
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    configurations = params['configurations']
    T_lat = params.get('T_lat', 0)
    epsilon = 1e-6

    for i in range(1, num_steps + 1):
        # (1) Message size constraint: sum of data volumes across all OCS should equal m_i[i] for each step i
        sum_d = sum(d[(i, j)] for j in range(1, k + 1))
        if abs(sum_d - m_i[i]) > epsilon:
            log.info(f"Step {i} message size constraint violated: sum(d)= {sum_d}, m_i[{i}]= {m_i[i]}")
            return False

        for j in range(1, k + 1):
            # (2) Bandwidth + latency constraint: t_end - t_start == d/B + T_lat * u
            expected_duration = d[(i, j)] / B + T_lat * u[(i, j)]
            if abs((t_end[(i, j)] - t_start[(i, j)]) - expected_duration) > epsilon:
                log.info(f"Step {i}, OCS {j} bandwidth+latency constraint violated: t_end-t_start= {t_end[(i, j)] - t_start[(i, j)]}, expected= {expected_duration}")
                return False

            # (3) Usage indicator constraint: if d>0, then u should be 1
            if d[(i, j)] > epsilon and u[(i, j)] < 0.5:
                log.info(f"Step {i}, OCS {j} usage indicator inconsistent: d= {d[(i, j)]}, u= {u[(i, j)]}")
                return False

            # (4) Reconfiguration time constraint: t_reconf_end - t_reconf_start == r * T_reconf
            if abs((t_reconf_end[(i, j)] - t_reconf_start[(i, j)]) - r[(i, j)] * T_reconf) > epsilon:
                log.info(f"Step {i}, OCS {j} reconfiguration time constraint violated: t_reconf_end-t_reconf_start= {t_reconf_end[(i, j)] - t_reconf_start[(i, j)]}, expected= {r[(i, j)] * T_reconf}")
                return False

            # (5) Transmission must start after reconfiguration completes
            if t_start[(i, j)] < t_reconf_end[(i, j)] - epsilon:
                log.info(f"Step {i}, OCS {j} transmission starts before reconfiguration ends: t_start= {t_start[(i, j)]}, t_reconf_end= {t_reconf_end[(i, j)]}")
                return False

            # (6) Configuration change indicator: for non-first steps, if config changes and u=1, then r should be 1
            if i > 1:
                if configurations[i] != configurations[i - 1] and u[(i, j)] > 0.5 and r[(i, j)] < 0.5:
                    log.info(f"Step {i}, OCS {j} configuration change indicator violated: u= {u[(i, j)]}, r= {r[(i, j)]}")
                    return False

        # (8) Step completion time definition: t_step_end[i] should equal max of all OCS (t_end * u)
        max_val = max(t_end[(i, j)] * u[(i, j)] for j in range(1, k + 1))
        if abs(t_step_end[i] - max_val) > epsilon:
            log.info(f"Step {i} completion time definition violated: t_step_end= {t_step_end[i]}, expected= {max_val}")
            return False

        # (9) Step dependency constraint: for i>1, transmission start time must not be earlier than previous step completion
        if i > 1:
            for j in range(1, k + 1):
                if t_start[(i, j)] < t_step_end[i - 1] - epsilon:
                    log.info(f"Step {i}, OCS {j} dependency constraint violated: t_start= {t_start[(i, j)]}, previous step completion time= {t_step_end[i - 1]}")
                    return False

    # (10) CCT definition: CCT should be greater than or equal to max of all step completion times
    if abs(cct - max(t_step_end[i] for i in range(1, num_steps + 1))) > epsilon:
        log.info(f"CCT definition violated: cct= {cct}, expected>= {max(t_step_end[i] for i in range(1, num_steps + 1))}")
        return False

    log.info("All constraints satisfied")
    return True

def load_and_validate_solution(params, filename, if_debug_model=False, solver='pulp'):
    """
    Load solution file, validate feasibility, and output validation results
    """
    cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = load_solution(params, filename, solver)
    valid = validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, if_debug_model)
    model_mode = "debug" if if_debug_model else "normal"
    log.info(f"Solution is {'feasible' if valid else 'infeasible'} in {model_mode} model\n")
    return valid