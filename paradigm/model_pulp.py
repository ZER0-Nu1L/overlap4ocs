import pulp

def build_model(params, debug_model=False):
    num_steps = params['num_steps']
    k = params['k']
    B = params['B']
    T_reconf = params['T_reconf']
    m_i = params['m_i']
    configurations = params['configurations']
    M = params['m']  # Large constant value for big-M method 
    M_time = 1e6

    d = {}
    t_start = {}
    t_end = {}
    t_reconf_start = {}
    t_reconf_end = {}
    u = {}
    r = {}
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            d[(i,j)] = pulp.LpVariable(f"d_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
            t_start[(i,j)] = pulp.LpVariable(f"t_start_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
            t_end[(i,j)] = pulp.LpVariable(f"t_end_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
            t_reconf_start[(i,j)] = pulp.LpVariable(f"t_reconf_start_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
            t_reconf_end[(i,j)] = pulp.LpVariable(f"t_reconf_end_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
            u[(i,j)] = pulp.LpVariable(f"u_{i}_{j}", cat=pulp.LpBinary)
            r[(i,j)] = pulp.LpVariable(f"r_{i}_{j}", cat=pulp.LpBinary)
    t_step_end = {}
    for i in range(1, num_steps+1):
        t_step_end[i] = pulp.LpVariable(f"t_step_end_{i}", lowBound=0, cat=pulp.LpContinuous)
    CCT = pulp.LpVariable("CCT", lowBound=0, cat=pulp.LpContinuous)

    if not debug_model:
        t_prev_end = {}
        # v[i,j] 表示 t_end[i,j]*u[i,j]
        # w[i,j] 表示 t_reconf_end[i,j]*r[i,j]
        v = {}
        w = {}
        for i in range(1, num_steps+1):
            for j in range(1, k+1):
                t_prev_end[(i,j)] = pulp.LpVariable(f"t_prev_end_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
                v[(i,j)] = pulp.LpVariable(f"v_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
                w[(i,j)] = pulp.LpVariable(f"w_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)

    prob = pulp.LpProblem("Optimization_with_overlapping_tech", pulp.LpMinimize)
    prob += CCT, "Minimize_CCT"

    # (1) Message size constraint
    for i in range(1, num_steps+1):
        prob += (pulp.lpSum(d[(i,j)] for j in range(1, k+1)) == m_i[i],
                 f"msg_size_step_{i}")

    # (2) Bandwidth constraint
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_end[(i,j)] - t_start[(i,j)] == (1.0 / B) * d[(i,j)],
                     f"bandwidth_step_{i}_{j}")

    # (3) Usage indicator variable constraint
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (d[(i,j)] <= u[(i,j)] * M, f"use_indicator_step_{i}_{j}")

    # (4) Reconfiguration time constraint
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_reconf_end[(i,j)] - t_reconf_start[(i,j)] == r[(i,j)] * T_reconf,
                     f"reconf_time_step_{i}_{j}")

    # (5) Dependency between transmission and reconfiguration
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_start[(i,j)] >= t_reconf_end[(i,j)],
                     f"trans_after_reconf_step_{i}_{j}")

    # (6) Configuration change indicator variable r_{i,j}
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            if i == 1:
                prob += (r[(i,j)] >= u[(i,j)], f"r_initial_step_{i}_{j}")
            else:
                # Check if configurations are the same
                same_config = 1 if configurations[i] == configurations[i-1] else 0
                prob += (r[(i,j)] >= u[(i,j)] - same_config, f"r_def_step_{i}_{j}")
            prob += (u[(i,j)] >= r[(i,j)], f"u_after_r_{i}_{j}")

    # (7) OCS activity time non-overlapping constraint
    if debug_model:
        for j in range(1, k+1):
            for i in range(2, num_steps+1):
                prob += (t_reconf_start[(i,j)] >= t_end[(i-1,j)],
                         f"reconf_after_prev_end_step_{i}_{j}")
                prob += (t_reconf_start[(i,j)] >= t_reconf_start[(i-1,j)],
                         f"reconf_after_prev_reconf_step_{i}_{j}")
    else:
        for j in range(1, k+1):
            prob += (t_prev_end[(1,j)] == 0, f"t_prev_end_step_1_{j}")
        for j in range(1, k+1):
            for i in range(2, num_steps+1):
                prob += (t_prev_end[(i,j)] >= t_prev_end[(i-1,j)],
                         f"t_prev_end_recursive_step_{i-1}_{j}")
                prob += (t_prev_end[(i,j)] >= v[(i-1,j)],
                         f"t_prev_end_trans_step_{i}_{j}")
                prob += (t_prev_end[(i,j)] >= w[(i-1,j)],
                         f"t_prev_end_reconf_step_{i}_{j}")
                prob += (t_reconf_start[(i,j)] >= t_prev_end[(i,j)],
                         f"reconf_after_prev_end_step_{i}_{j}")

        for i in range(1, num_steps+1):
            for j in range(1, k+1):
                # v[i,j] = t_end[i,j] * u[i,j]
                prob += (v[(i,j)] <= M_time * u[(i,j)],
                         f"v_ub1_{i}_{j}")
                prob += (v[(i,j)] <= t_end[(i,j)],
                         f"v_ub2_{i}_{j}")
                prob += (v[(i,j)] >= t_end[(i,j)] - M_time * (1 - u[(i,j)]),
                         f"v_lb_{i}_{j}")
                # w[i,j] = t_reconf_end[i,j] * r[i,j]
                prob += (w[(i,j)] <= M_time * r[(i,j)],
                         f"w_ub1_{i}_{j}")
                prob += (w[(i,j)] <= t_reconf_end[(i,j)],
                         f"w_ub2_{i}_{j}")
                prob += (w[(i,j)] >= t_reconf_end[(i,j)] - M_time * (1 - r[(i,j)]),
                         f"w_lb_{i}_{j}")

    # (8) Step completion time definition
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            if debug_model:
                prob += (t_step_end[i] >= t_end[(i,j)],
                         f"step_end_step_{i}_{j}")
            else:
                prob += (t_step_end[i] >= v[(i,j)],
                         f"step_end_step_{i}_{j}")

    # (9) Step dependency constraint
    for i in range(2, num_steps+1):
        for j in range(1, k+1):
            prob += (t_start[(i,j)] >= t_step_end[i-1],
                     f"trans_after_prev_step_end_step_{i}_{j}")

    # (10) Communication completion time definition
    for i in range(1, num_steps+1):
        prob += (CCT >= t_step_end[i], f"CCT_def_step_{i}")

    return prob, CCT, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end