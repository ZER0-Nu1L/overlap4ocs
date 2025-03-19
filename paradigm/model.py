import gurobipy as gp
from gurobipy import GRB
import os, json
import logging as log


def build_model(params, debug_model=False):
    model = gp.Model("Optimization_with_overlapping_tech")
    model.setParam('LogToConsole', 0)  # 1 表示输出到控制台，0 表示不输出
    model.setParam('OutputFlag', 0)  # 1 表示启用输出，0 表示禁用所有输出
    model.setParam('LogFile', './log/gurobi.log')  # 将日志输出到文件

    k = params['k']
    num_steps = params['num_steps']
    configurations = params['configurations']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    M = params['m']  # 大常数
    M_config = max(configurations.values())

    # 定义变量
    d = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="d")
    t_start = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_start")
    t_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_end")
    u = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="u")
    r = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="r")
    t_reconf_start = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_reconf_start")
    t_reconf_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_reconf_end")
    t_step_end = model.addVars(range(1, num_steps + 1), vtype=GRB.CONTINUOUS, name="t_step_end")
    cct = model.addVar(vtype=GRB.CONTINUOUS, name="CCT")

    # 定义辅助变量
    same_config = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.BINARY, name="same_config")
    t_prev_end = model.addVars(range(1, num_steps + 1), range(1, k + 1), vtype=GRB.CONTINUOUS, name="t_prev_end")

    # 设置目标函数
    model.setObjective(cct, GRB.MINIMIZE)

    # 添加约束
    add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end,
                    same_config, t_prev_end, cct, debug_model)
    return model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end


def add_constraints(model, params, d, t_start, t_end, u, r,
                    t_reconf_start, t_reconf_end, t_step_end, same_config, t_prev_end, CCT, debug_model=False):
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    M = params['m']
    configurations = params['configurations']

    # (1) 消息大小约束
    for i in range(1, num_steps + 1):
        model.addConstr(gp.quicksum(d[i, j] for j in range(1, k + 1)) == m_i[i],
                        name=f"msg_size_step_{i}")

    # (2) 带宽限制约束
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_end[i, j] - t_start[i, j] == d[i, j] / B,
                            name=f"bandwidth_step_{i}_ocs_{j}")

    # (3) 使用指示变量约束
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
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
        for j in range(1, k + 1):
            model.addConstr(t_reconf_end[i, j] - t_reconf_start[i, j] == r[i, j] * T_reconf,
                            name=f"reconf_time_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] <= 1,
                            name=f"r_binary_upper_step_{i}_ocs_{j}")
            model.addConstr(r[i, j] >= 0,
                            name=f"r_binary_lower_step_{i}_ocs_{j}")

    # (5) 传输与重配置的依赖关系
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_start[i, j] >= t_reconf_end[i, j],
                            name=f"trans_after_reconf_step_{i}_ocs_{j}")

    # (6) 配置变化指示变量 r_{i,j}
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            if i == 1:
                # 初始步骤，没有上一次配置，假设需要重配置
                model.addConstr(r[i, j] >= u[i, j],
                                name=f"r_initial_step_{i}_ocs_{j}")
            else:
                # 判断配置是否相同
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

    # NOTE: 配置是为传输服务的
    for j in range(1, k + 1):
        for i in range(1, num_steps + 1):
            model.addConstr(u[i, j] >= r[i, j],
                            name=f"u_after_r_{i}_ocs_{j}")          

    # (7) OCS 活动时间不重叠约束
    if debug_model:
        # pass
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
                # 重配置开始时间不早于上一次活动结束时间
                model.addConstr(t_reconf_start[i, j] >= t_prev_end[i, j],
                                name=f"reconf_after_prev_end_step_{i}_ocs_{j}")

    # (8) 步骤完成时间定义
    for i in range(1, num_steps + 1):
        for j in range(1, k + 1):
            model.addConstr(t_step_end[i] >= t_end[i, j] * u[i, j],
                            name=f"step_end_step_{i}_ocs_{j}")

    # (9) 步骤依赖性约束
    if debug_model:
        for i in range(2, num_steps + 1):
            for j in range(1, k + 1):
                model.addConstr(
                    t_step_end[i - 1] <= t_start[i, j] + M * (1 - u[i, j]),
                    name=f"step_end_before_start_step_{i}_ocs_{j}"
                )
    else:
        for i in range(2, num_steps + 1):
            for j in range(1, k + 1):
                model.addConstr(t_start[i, j] >= t_step_end[i - 1],
                                name=f"trans_after_prev_step_end_step_{i}_ocs_{j}")

    # (10) 通信完成时间定义
    # model.addConstr(CCT >= t_step_end[num_steps]) # TODO: FIXME:
    for i in range(1, num_steps + 1):
        model.addConstr(CCT >= t_step_end[i],
                        name=f"CCT_def_step_{i}")

def optimize_model(model):
    model.optimize()
    return model


def _load_solution(params, filename):
    # 检查文件是否存在
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Solution file {filename} not found.")
    
    with open(filename, 'r') as file:
        solution_data = json.load(file)
    
    # 创建字典来存储变量的值
    var_dict = {v['VarName']: v['X'] for v in solution_data['Vars']}
    
    # 检查参数是否匹配
    if 'CCT' not in var_dict:
        raise ValueError("Solution file does not contain 'CCT' variable.")
    
    def get_var(name, default=None):
        return var_dict.get(name, default)
    
    cct = get_var('CCT')
    if cct is None:
        raise ValueError("Solution file does not contain 'CCT' variable.")
    
    # 初始化变量
    d = {}
    t_start = {}
    t_end = {}
    u = {}
    r = {}
    t_reconf_start = {}
    t_reconf_end = {}
    t_step_end = {}
    
    # 填充变量
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
    
    # 转化为能用索引访问的数据结构
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
    configurations = params['configurations']
    
    epsilon = 1e-6  # 用于浮点数比较的误差容忍度

    # 检查所有约束
    for i in range(1, num_steps + 1):
        # (1) 消息大小约束
        if abs(sum(d[i, j] for j in range(1, k + 1)) - m_i[i]) > epsilon:
            log.info("#Constrain: sum(d[i, j] for j in range(1, k + 1)) - m_i[i]")
            log.info(f"sum_j(d[{i}, j]) = {sum(d[i, j] for j in range(1, k + 1))}")
            log.info(f"m_i[{i}] = {m_i[i]}")
            log.info(f"违反约束: 步骤 {i} 的消息大小不匹配")
            return False

        for j in range(1, k + 1):
            # (2) 带宽限制约束
            if abs((t_end[i, j] - t_start[i, j]) - d[i, j] / B) > epsilon:
                log.info("#Constrain: (t_end[i, j] - t_start[i, j]) - d[i, j] / B")
                log.info(f"t_end[{i}, {j}] = {t_end[i, j]}")
                log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                log.info(f"d[{i}, {j}] = {d[i, j]}")
                log.info(f"违反约束: 步骤 {i}, OCS {j} 的带宽限制不满足")
                return False

            # (3) 使用指示变量约束
            if d[i, j] > 0 and u[i, j] == 0:
                log.info("#Constrain: d[i, j] > 0 and u[i, j] == 0")
                log.info(f"d[{i}, {j}] = {d[i, j]}")
                log.info(f"u[{i}, {j}] = {u[i, j]}")
                log.info(f"违反约束: 步骤 {i}, OCS {j} 的使用指示变量不一致")
                return False

            # (4) 重配置时间约束
            if abs((t_reconf_end[i, j] - t_reconf_start[i, j]) - r[i, j] * T_reconf) > epsilon:
                log.info("#Constrain: (t_reconf_end[i, j] - t_reconf_start[i, j]) - r[i, j] * T_reconf")
                log.info(f"t_reconf_end[{i}, {j}] = {t_reconf_end[i, j]}")
                log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                log.info(f"r[{i}, {j}] = {r[i, j]}")
                log.info(f"违反约束: 步骤 {i}, OCS {j} 的重配置时间不正确")
                return False

            # (5) 传输与重配置的依赖关系
            if t_start[i, j] < t_reconf_end[i, j]:
                log.info("#Constrain: t_start[i, j] < t_reconf_end[i, j]")
                log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                log.info(f"t_reconf_end[{i}, {j}] = {t_reconf_end[i, j]}")
                log.info(f"违反约束: 步骤 {i}, OCS {j} 的传输开始时间早于重配置结束时间")
                return False

            # (6) 配置变化指示变量 r_{i,j}
            if i > 1:
                if configurations[i] != configurations[i-1] and u[i, j] == 1 and r[i, j] == 0:
                    log.info("#Constrain: configurations[i] != configurations[i-1] and u[i, j] == 1 and r[i, j] == 0")
                    log.info(f"configurations[{i}] = {configurations[i]}")
                    log.info(f"configurations[{i-1}] = {configurations[i-1]}")
                    log.info(f"u[{i}, {j}] = {u[i, j]}")
                    log.info(f"r[{i}, {j}] = {r[i, j]}")
                    log.info(f"违反约束: 步骤 {i}, OCS {j} 的配置变化指示变量不正确")
                    return False

            # (8) OCS 活动时间不重叠约束
            if i > 1:
                if debug_model:
                    reconf_after_prev_end_satisfied = t_reconf_start[i, j] >= t_end[i-1, j]
                    # reconf_after_prev_reconf_satisfied = t_reconf_start[i, j] >= t_reconf_start[i-1, j]

                    if not reconf_after_prev_end_satisfied:
                        log.info("#Constrain: t_reconf_start[i, j] >= t_end[i-1, j]")
                        log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                        log.info(f"t_end[{i-1}, {j}] = {t_end[i-1, j]}")
                        log.info(f"违反约束: reconf_after_prev_end_step_{i}_ocs_{j}")
                        return False

                    # if not reconf_after_prev_reconf_satisfied:
                    #     log.info("#Constrain: t_reconf_start[i, j] >= t_reconf_start[i-1, j]")
                    #     log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                    #     log.info(f"t_reconf_start[{i-1}, {j}] = {t_reconf_start[i-1, j]}")
                    #     log.info(f"违反约束: reconf_after_prev_reconf_step_{i}_ocs_{j}")
                    #     return False
                else:
                    prev_end = max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])
                    if t_reconf_start[i, j] < prev_end:
                        log.info("#Constrain: t_reconf_start[i, j] < prev_end")
                        log.info("prev_end = max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])")
                        log.info(
                            f"prev_end = max(t_end[{i-1}, {j}] * u[{i-1}, {j}], t_reconf_end[{i-1}, {j}] * r[{i-1}, {j}])"
                            f"= max({t_end[i-1, j]} * {u[i-1, j]}, {t_reconf_end[i-1, j]} * {r[i-1, j]}) "
                            f"= {max(t_end[i-1, j] * u[i-1, j], t_reconf_end[i-1, j] * r[i-1, j])}"
                            )
                        log.info(f"t_reconf_start[{i}, {j}] = {t_reconf_start[i, j]}")
                        log.info(f"违反约束: 步骤 {i}, OCS {j} 的活动时间重叠")
                        return False
                    

        # (9) 步骤完成时间定义
        step_end = max(t_end[i, j] * u[i, j] for j in range(1, k + 1))
        if abs(t_step_end[i] - step_end) > epsilon:
            log.info("#Constrain: t_step_end[i] - step_end")
            log.info("step_end = max(t_end[i, j] * u[i, j] for j in range(1, k + 1))")
            log.info(
                f"step_end = max(t_end[{i}, j] * u[{i}, j] j forall )"
                f"= {max(t_end[i, j] * u[i, j] for j in range(1, k + 1))}"
                )
            log.info(f"违反约束: 步骤 {i} 的完成时间定义不正确")
            return False

        # (10) 步骤依赖性约束
        if i > 1:
            for j in range(1, k + 1):
                if t_start[i, j] < t_step_end[i-1]:
                    log.info("#Constrain: u[i, j] * t_start[i, j] < t_step_end[i-1]")
                    log.info(f"u[{i}, {j}] = {u[i, j]}") # DEBUG:
                    log.info(f"t_start[{i}, {j}] = {t_start[i, j]}")
                    log.info(f"t_step_end[{i-1}] = {t_step_end[i-1]}")
                    log.info(f"违反约束: 步骤 {i}, OCS {j} 的开始时间早于上一步骤的完成时间")
                    return False

    # (11) 通信完成时间定义
    if abs(cct - max(t_step_end[i] for i in range(1, num_steps + 1))) > epsilon:
        log.info("违反约束: 通信完成时间定义不正确")
        return False

    log.info("所有约束都满足")
    return True

def load_and_validate_solution(params, filename, if_debug_model=False):
    # cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end 并非 Gurobi Vars 格式
    # 是从 JSON 中解析出来后，自定义的格式，可以用类似 Gurobi Vars 索引的形式访问
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
    
    model_mode = "调试" if if_debug_model else "正常"
    log.info(f"解在{model_mode}模型中是{'可行' if is_valid_for_model else '不可行'}的\n")