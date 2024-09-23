import gurobipy as gp
from gurobipy import GRB


def build_model(params):
    model = gp.Model("Optimization_with_overlapping_tech")

    k = params['k']
    num_steps = params['num_steps']
    configurations = params['configurations']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    M = params['m']  # 大常数
    M_config = max(configurations.values())

    # 定义变量
    d = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="d")
    t_start = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="t_start")
    t_end = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="t_end")
    u = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.BINARY, name="u")
    r = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.BINARY, name="r")
    t_reconf_start = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="t_reconf_start")
    t_reconf_end = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="t_reconf_end")
    t_step_end = model.addVars(range(1, num_steps + 1), vtype=GRB.CONTINUOUS, name="t_step_end")
    cct = model.addVar(vtype=GRB.CONTINUOUS, name="CCT")

    # 定义辅助变量
    delta = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.BINARY, name="delta")
    same_config = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.BINARY, name="same_config")
    t_prev_end = model.addVars(range(1, num_steps + 1), range(k), vtype=GRB.CONTINUOUS, name="t_prev_end")

    # 设置目标函数
    model.setObjective(cct, GRB.MINIMIZE)

    # 添加约束
    add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end,
                    delta, same_config, t_prev_end, cct)

    return model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end


def add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end,
                    delta, same_config, t_prev_end, CCT):
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    M = params['m']
    configurations = params['configurations']

    # (1) 消息大小约束
    for i in range(1, num_steps + 1):
        model.addConstr(gp.quicksum(d[i, j] for j in range(k)) == m_i[i],
                        name=f"msg_size_step_{i}")

    # (2) 带宽限制约束
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(t_end[i, j] - t_start[i, j] == d[i, j] / B,
                            name=f"bandwidth_step_{i}_ocs_{j}")

    # (3) 使用指示变量约束
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(d[i, j] <= u[i, j] * M,
                            name=f"use_indicator_step_{i}_ocs_{j}")
            model.addConstr(d[i, j] >= 0,
                            name=f"d_nonnegative_step_{i}_ocs_{j}")
            model.addConstr(u[i, j] <= 1,
                            name=f"u_binary_upper_step_{i}_ocs_{j}")
            model.addConstr(u[i, j] >= 0,
                            name=f"u_binary_lower_step_{i}_ocs_{j}")

    # (4) 重配置时间约束
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(t_reconf_end[i, j] - t_reconf_start[i, j] == r[i, j] * T_reconf,
                            name=f"reconf_time_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] <= 1,
                            name=f"r_binary_upper_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] >= 0,
                            name=f"r_binary_lower_step_{i}_ocs_{j}")

    # (5) 传输与重配置的依赖关系
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(t_start[i, j] >= t_reconf_end[i, j],
                            name=f"trans_after_reconf_step_{i}_ocs_{j}")

    # (6) OCS 活动时间不重叠约束
    for j in range(k):
        for i in range(1, num_steps + 1):
            if i == 1:
                model.addConstr(t_prev_end[i, j] == 0,
                                name=f"t_prev_end_step_{i}_ocs_{j}")
            else:
                model.addConstr(t_prev_end[i, j] >= t_end[i - 1, j] * u[i - 1, j],
                                name=f"t_prev_end_trans_step_{i}_ocs_{j}")
                model.addConstr(t_prev_end[i, j] >= t_reconf_end[i - 1, j] * r[i - 1, j],
                                name=f"t_prev_end_reconf_step_{i}_ocs_{j}")
            # 重配置开始时间不早于上一次活动结束时间
            model.addConstr(t_reconf_start[i, j] >= t_prev_end[i, j],
                            name=f"reconf_after_prev_end_step_{i}_ocs_{j}")

    # (7) 配置变化指示变量 delta_{i,j}
    for i in range(1, num_steps + 1):
        for j in range(k):
            if i == 1:
                # 初始步骤，没有上一次配置，假设需要重配置
                model.addConstr(delta[i, j] >= u[i, j],
                                name=f"delta_initial_step_{i}_ocs_{j}")
            else:
                # 判断配置是否相同
                config_diff = abs(configurations[i] - configurations[i - 1])
                if config_diff == 0:
                    model.addConstr(same_config[i, j] == 1,
                                    name=f"same_config_step_{i}_ocs_{j}")
                else:
                    model.addConstr(same_config[i, j] == 0,
                                    name=f"same_config_step_{i}_ocs_{j}")
                # delta_{i,j} >= u_{i,j} * (1 - same_config_{i,j})
                model.addConstr(delta[i, j] >= u[i, j] - same_config[i, j],
                                name=f"delta_def_step_{i}_ocs_{j}")

    # (8) 重配置需求约束
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(r[i, j] >= delta[i, j],
                            name=f"reconf_need_step_{i}_ocs_{j}")

    # (9) 步骤完成时间定义
    for i in range(1, num_steps + 1):
        for j in range(k):
            model.addConstr(t_step_end[i] >= t_end[i, j] * u[i, j],
                            name=f"step_end_step_{i}_ocs_{j}")

    # (10) 步骤依赖性约束
    for i in range(2, num_steps + 1):
        for j in range(k):
            model.addConstr(t_start[i, j] >= t_step_end[i - 1],
                            name=f"trans_after_prev_step_end_step_{i}_ocs_{j}")

    # (11) 通信完成时间定义
    for i in range(1, num_steps + 1):
        model.addConstr(CCT >= t_step_end[i],
                        name=f"CCT_def_step_{i}")


def optimize_model(model):
    model.optimize()
    return model
