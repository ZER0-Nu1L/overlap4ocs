import gurobipy as gp
from gurobipy import GRB
import os, json
import logging as log


def compute_bigM(params):
    """
    Compute appropriate Big-M value for the MILP model.

    Big-M should be large enough to not constrain the problem,
    but not so large as to cause numerical issues.

    For data volume constraints: M >= max message size
    For time constraints: M >= theoretical upper bound on CCT
    """
    m = params['m']
    k = params['k']
    B = params['B']
    T_reconf = params['T_reconf']
    num_steps = params.get('num_steps', 1)

    # Conservative upper bound on CCT:
    # Worst case: all data on one OCS + all reconfigurations
    max_transmission_time = m / B
    max_reconfig_time = num_steps * T_reconf
    theoretical_upper_bound = max_transmission_time + max_reconfig_time

    # Big-M for data volume: use max message size with safety factor
    M_data = max(m, max(params['m_i'].values()) if 'm_i' in params else m) * 1.5

    # Big-M for time: use theoretical upper bound with safety factor
    M_time = theoretical_upper_bound * 2

    return M_data, M_time


def build_model(params, debug_model=False):
    model = gp.Model("Optimization_with_overlapping_tech")
    model.setParam('LogToConsole', 0)  # NOTE: 1 means output to console, 0 means no output
    model.setParam('OutputFlag', 0)    # NOTE: 1 enables output, 0 disables all output
    # Create logs directory if it doesn't exist
    if not os.path.exists('./logs'):
        os.makedirs('./logs')
    model.setParam('LogFile', './logs/gurobi.log')  # NOTE: Log output to a file

    k = params['k']
    num_steps = params['num_steps']
    configurations = params['configurations']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    T_lat = params.get('T_lat', 0)
    M_data, M_time = compute_bigM(params)  # Robust Big-M values
    M_config = max(configurations.values())

    # Variables
    d = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="d")
    t_start = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_start")
    t_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_end")
    u = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="u")
    r = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="r")
    t_reconf_start = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_reconf_start")
    t_reconf_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_reconf_end")
    t_step_end = model.addVars(range(1, num_steps + 1), vtype=GRB.CONTINUOUS, name="t_step_end")
    cct = model.addVar(vtype=GRB.CONTINUOUS, name="CCT")

    # Intermediate Variables
    same_config = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="same_config")
    t_prev_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_prev_end")

    # Objective function
    model.setObjective(cct, GRB.MINIMIZE)

    # Constraints
    add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end,
                    same_config, t_prev_end, cct, T_lat, debug_model)
    return model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end


def add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end, same_config, t_prev_end, CCT, T_lat, debug_model=False):
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    M_data, M_time = compute_bigM(params)
    configurations = params['configurations']

    # (1) Message size constraint
    for i in range(1, num_steps + 1):
        model.addConstr(gp.quicksum(d[i, j] for j in range(1, k + 1)) == m_i[i],
                        name=f"msg_size_step_{i}")

    # (2) Bandwidth constraint
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_end[i, j] - t_start[i, j] == d[i, j] / B + T_lat * u[i, j],
                            name=f"bandwidth_step_{i}_ocs_{j}")

    # (3) Usage indicator variable constraint
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(d[i, j] <= u[i, j] * M_data,
                            name=f"use_indicator_step_{i}_ocs_{j}")
            model.addConstr(d[i, j] >= 0,
                            name=f"d_nonnegative_step_{i}_ocs_{j}")
            model.addConstr(u[i, j] <= 1,
                            name=f"u_binary_upper_step_{i}_ocs_{j}")
            model.addConstr(u[i, j] >= 0,
                            name=f"u_binary_lower_step_{i}_ocs_{j}")

    # (4) Reconfiguration time constraint
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_reconf_end[i, j] - t_reconf_start[i, j] == r[i, j] * T_reconf,
                            name=f"reconf_time_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] <= 1,
                            name=f"r_binary_upper_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] >= 0,
                            name=f"r_binary_lower_step_{i}_ocs_{j}")

    # (5) Dependency between transmission and reconfiguration
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_start[i, j] >= t_reconf_end[i, j],
                            name=f"trans_after_reconf_step_{i}_ocs_{j}")

    # (6) Configuration change indicator variable r_{i,j}
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            if i == 1:
                # Initial step, no previous configuration, assume reconfiguration is needed
                model.addConstr(r[i, j] >= u[i, j],
                                name=f"r_initial_step_{i}_ocs_{j}")
            else:
                # Check if configurations are the same
                config_diff = abs(configurations[i] - configurations[i - 1])
                if config_diff == 0:
                    model.addConstr(same_config[i, j] == 1,
                                    name=f"same_config_step_{i}_ocs_{j}")
                else:
                    model.addConstr(same_config[i, j] == 0,
                                    name=f"same_config_step_{i}_ocs_{j}")
                # r_{i,j} >= u_{i,j} * (1 - same_config_{i,j})
                model.addConstr(r[i, j] >= u[i, j] - same_config[i, j],
                                name=f"r_def_step_{i}_ocs_{j}")

    # NOTE: Configuration serves transmission
    for j in range(1, k + 1):
        for i in range(1, num_steps + 1):
            model.addConstr(u[i, j] >= r[i, j],
                            name=f"u_after_r_{i}_ocs_{j}")          

    # (7) OCS activity time non-overlapping constraint
    if debug_model:
        for j in range(1, k + 1):
            for i in range(2, num_steps + 1):
                model.addConstr(t_reconf_start[i, j] >= t_end[i-1, j],
                                name=f"reconf_after_prev_end_step_{i}_ocs_{j}")
                model.addConstr(t_reconf_start[i, j] >= t_reconf_start[i-1, j],
                                name=f"reconf_after_prev_reconf_step_{i}_ocs_{j}")
    else:
        for j in range(1, k + 1):
            for i in range(1, num_steps + 1):
                if i == 1:
                    model.addConstr(t_prev_end[i, j] == 0,
                                    name=f"t_prev_end_step_{i}_ocs_{j}")
                else:
                    model.addConstr(t_prev_end[i, j] >= t_prev_end[i - 1, j],
                                    name=f"t_prev_end_recursive_step_{i-1}_ocs_{j}")
                    model.addConstr(t_prev_end[i, j] >= t_end[i - 1, j] * u[i - 1, j],
                                    name=f"t_prev_end_trans_step_{i}_ocs_{j}")
                    model.addConstr(t_prev_end[i, j] >= t_reconf_end[i - 1, j] * r[i - 1, j],
                                    name=f"t_prev_end_reconf_step_{i}_ocs_{j}")
                # Reconfiguration start time must not be earlier than the end of the previous activity
                model.addConstr(t_reconf_start[i, j] >= t_prev_end[i, j],
                                name=f"reconf_after_prev_end_step_{i}_ocs_{j}")

    # (8) Step completion time definition
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_step_end[i] >= t_end[i, j] * u[i, j],
                            name=f"step_end_step_{i}_ocs_{j}")

    # (9) Step dependency constraint
    if debug_model:
        for i in range(2, num_steps + 1):
            for j in range(1, k + 1):
                model.addConstr(
                    t_step_end[i - 1] <= t_start[i, j] + M_time * (1 - u[i, j]),
                    name=f"step_end_before_start_step_{i}_ocs_{j}"
                )
    else:
        for i in range(2, num_steps + 1):
            for j in range(1, k + 1):
                model.addConstr(t_start[i, j] >= t_step_end[i - 1],
                                name=f"trans_after_prev_step_end_step_{i}_ocs_{j}")

    # (10) Communication completion time definition
    # model.addConstr(CCT >= t_step_end[num_steps]) # TODO: FIXME:
    for i in range(1, num_steps + 1):
        model.addConstr(CCT >= t_step_end[i],
                        name=f"CCT_def_step_{i}")


def optimize_model(model):
    model.optimize()
    return model


def _load_solution(params, filename):
    # Check if the file exists
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Solution file {filename} not found.")
    
    with open(filename, 'r') as file:
        solution_data = json.load(file)
    
    # Create a dictionary to store variable values
    var_dict = {v['VarName']: v['X'] for v in solution_data['Vars']}
    
    # Verify if the required parameters are present
    if 'CCT' not in var_dict:
        raise ValueError("Solution file does not contain 'CCT' variable.")
    
    def get_var(name, default=None):
        return var_dict.get(name, default)
    
    cct = get_var('CCT')
    if cct is None:
        raise ValueError("Solution file does not contain 'CCT' variable.")
    
    # Initialize variables
    d = {}
    t_start = {}
    t_end = {}
    u = {}
    r = {}
    t_reconf_start = {}
    t_reconf_end = {}
    t_step_end = {}
    
    # Populate variables
    for i in range(1, params['num_steps'] + 1):
        for j in range(1, params['k'] + 1):
            d[(i, j)] = get_var(f'd[{i},{j}]', 0)
            t_start[(i, j)] = get_var(f't_start[{i},{j}]', 0)
            t_end[(i, j)] = get_var(f't_end[{i},{j}]', 0)
            u[(i, j)] = get_var(f'u[{i},{j}]', 0)
            r[(i, j)] = get_var(f'r[{i},{j}]', 0)
            t_reconf_start[(i, j)] = get_var(f't_reconf_start[{i},{j}]', 0)
            t_reconf_end[(i, j)] = get_var(f't_reconf_end[{i},{j}]', 0)
        
        t_step_end[i] = get_var(f't_step_end[{i}]', 0)
    
    # Convert to data structures that support indexing
    d = {k: v for k, v in d.items()}
    t_start = {k: v for k, v in t_start.items()}
    t_end = {k: v for k, v in t_end.items()}
    u = {k: v for k, v in u.items()}
    r = {k: v for k, v in r.items()}
    t_reconf_start = {k: v for k, v in t_reconf_start.items()}
    t_reconf_end = {k: v for k, v in t_reconf_end.items()}
    t_step_end = {k: v for k, v in t_step_end.items()}
    
    return cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end


def _validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, debug_model=False):
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    T_lat = params.get('T_lat', 0)
    configurations = params['configurations']

    epsilon = 1e-6  # Tolerance for floating-point comparisons

    # Check all constraints
    for i in range(1, num_steps + 1):
        # (1) Message size constraint
        if abs(sum(d[i, j] for j in range(1, k + 1)) - m_i[i]) > epsilon:
            log.info("#Constraint: sum(d[i, j] for j in range(1, k + 1)) - m_i[i]")
            log.info(f"sum_j(d[{i}, j]) = {sum(d[i, j] for j in range(1, k + 1))}")
            log.info(f"m_i[{i}] = {m_i[i]}")
            log.info(f"Constraint violated: Message size mismatch at step {i}")
            return False

        for j in range(1, k + 1):
            # (2) Bandwidth constraint
            if abs((t_end[i, j] - t_start[i, j]) - (d[i, j] / B + T_lat * u[i, j])) > epsilon:
                log.info("#Constraint: (t_end[i, j] - t_start[i, j]) - (d[i, j] / B + T_lat * u[i, j])")
                log.info(f"t_end[{i}, {j}] = {t_end[i, j]}")
                log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                log.info(f"d[{i}, {j}] = {d[i, j]}")
                log.info(f"u[{i}, {j}] = {u[i, j]}")
                log.info(f"Constraint violated: Bandwidth limit not satisfied at step {i}, OCS {j}")
                return False

            # (3) Usage indicator variable constraint
            if d[i, j] > 0 and u[i, j] == 0:
                log.info("#Constraint: d[i, j] > 0 and u[i, j] == 0")
                log.info(f"d[{i}, {j}] = {d[i, j]}")
                log.info(f"u[{i}, {j}] = {u[i, j]}")
                log.info(f"Constraint violated: Usage indicator variable inconsistency at step {i}, OCS {j}")
                return False

            # (4) Reconfiguration time constraint
            if abs((t_reconf_end[i, j] - t_reconf_start[i, j]) - r[i, j] * T_reconf) > epsilon:
                log.info("#Constraint: (t_reconf_end[i, j] - t_reconf_start[i, j]) - r[i, j] * T_reconf")
                log.info(f"t_reconf_end[{i}, {j}] = {t_reconf_end[i, j]}")
                log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                log.info(f"r[{i}, {j}] = {r[i, j]}")
                log.info(f"Constraint violated: Reconfiguration time incorrect at step {i}, OCS {j}")
                return False

            # (5) Dependency between transmission and reconfiguration
            if t_start[i, j] < t_reconf_end[i, j]:
                log.info("#Constraint: t_start[i, j] < t_reconf_end[i, j]")
                log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                log.info(f"t_reconf_end[{i}, {j}] = {t_reconf_end[i, j]}")
                log.info(f"Constraint violated: Transmission start time earlier than reconfiguration end time at step {i}, OCS {j}")
                return False

            # (6) Configuration change indicator variable r_{i,j}
            if i > 1:
                if configurations[i] != configurations[i-1] and u[i, j] == 1 and r[i, j] == 0:
                    log.info("#Constraint: configurations[i] != configurations[i-1] and u[i, j] == 1 and r[i, j] == 0")
                    log.info(f"configurations[{i}] = {configurations[i]}")
                    log.info(f"configurations[{i-1}] = {configurations[i-1]}")
                    log.info(f"u[{i}, {j}] = {u[i, j]}")
                    log.info(f"r[{i}, {j}] = {r[i, j]}")
                    log.info(f"Constraint violated: Configuration change indicator variable incorrect at step {i}, OCS {j}")
                    return False

            # (8) OCS activity time non-overlapping constraint
            if i > 1:
                if debug_model:
                    reconf_after_prev_end_satisfied = t_reconf_start[i, j] >= t_end[i-1, j]

                    if not reconf_after_prev_end_satisfied:
                        log.info("#Constraint: t_reconf_start[i, j] >= t_end[i-1, j]")
                        log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                        log.info(f"t_end[{i-1}, {j}] = {t_end[i-1, j]}")
                        log.info(f"Constraint violated: reconf_after_prev_end_step_{i}_ocs_{j}")
                        return False
                else:
                    prev_end = max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])
                    if t_reconf_start[i, j] < prev_end:
                        log.info("#Constraint: t_reconf_start[i, j] < prev_end")
                        log.info("prev_end = max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])")
                        log.info(
                            f"prev_end = max(t_end[{i-1}, {j}] * u[{i-1}, {j}], t_reconf_end[{i-1}, {j}] * r[{i-1}, {j}])"
                            f"= max({t_end[i-1, j]} * {u[i-1, j]}, {t_reconf_end[i-1, j]} * {r[i-1, j]}) "
                            f"= {max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])}"
                            )
                        log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                        log.info(f"Constraint violated: Activity time overlap at step {i}, OCS {j}")
                        return False

        # (9) Step completion time definition
        step_end = max(t_end[i, j] * u[i, j] for j in range(1, k + 1))
        if abs(t_step_end[i] - step_end) > epsilon:
            log.info("#Constraint: t_step_end[i] - step_end")
            log.info("step_end = max(t_end[i, j] * u[i, j] for j in range(1, k + 1))")
            log.info(
                f"step_end = max(t_end[{i}, j] * u[{i}, j] j forall )"
                f"= {max(t_end[i, j] * u[i, j] for j in range(1, k + 1))}"
                )
            log.info(f"Constraint violated: Step completion time definition incorrect at step {i}")
            return False

        # (10) Step dependency constraint
        if i > 1:
            for j in range(1, k + 1):
                if t_start[i, j] < t_step_end[i-1]:
                    log.info("#Constraint: u[i, j] * t_start[i, j] < t_step_end[i-1]")
                    log.info(f"u[{i}, {j}] = {u[i, j]}") # DEBUG:
                    log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                    log.info(f"t_step_end[{i-1}] = {t_step_end[i-1]}")
                    log.info(f"Constraint violated: Start time earlier than previous step completion time at step {i}, OCS {j}")
                    return False

    # (11) Communication completion time definition
    if abs(cct - max(t_step_end[i] for i in range(1, num_steps + 1))) > epsilon:
        log.info("Constraint violated: Communication completion time definition incorrect")
        return False

    log.info("All constraints are satisfied")
    return True


def load_and_validate_solution(params, filename, if_debug_model=False):
    # cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end are not in Gurobi Vars format
    # They are custom formats parsed from JSON and can be accessed using Gurobi-like indexing
    cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = _load_solution(params, filename)
    # variables = {
    #     "cct": cct,
    #     "d": d,
    #     "t_start": t_start,
    #     "t_end": t_end,
    #     "u": u,
    #     "r": r,
    #     "t_reconf_start": t_reconf_start,
    #     "t_reconf_end": t_reconf_end,
    #     "t_step_end": t_step_end
    # }
    # for name, value in variables.items():
    #     log.info(f"{name}: {value}")
    
    is_valid_for_model = _validate_solution(params, 
                                           d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, 
                                           if_debug_model)
    
    model_mode = "debug" if if_debug_model else "normal"
    log.info(f"The solution is {'feasible' if is_valid_for_model else 'infeasible'} in the {model_mode} model\n")