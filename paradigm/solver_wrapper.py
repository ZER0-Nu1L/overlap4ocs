import os
import json
import logging as log
from utils import check_platform

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
    elif solver == 'pulp' or solver == 'copt':
        solution = {}
        for var in model.variables():
            solution[var.name] = var.varValue
        with open(filename, 'w') as f:
            json.dump(solution, f, indent=4)
    else:
        raise ValueError(f"Unsupported solver: {solver}")

def solve_model(model, solver):
    """
    Solve the model using the specified solver.
    """
    if solver == 'gurobi':
        model.optimize()
    elif solver == 'pulp':
        import pulp
        import multiprocessing
        num_threads = multiprocessing.cpu_count()

        # For Arm-based Mac platforms.
        # Reference: https://github.com/tyler-griggs/melange-release/blob/main/melange/solver.py
        if check_platform.is_arm_mac():
            solver = pulp.getSolver('COIN_CMD', path='/opt/homebrew/opt/cbc/bin/cbc', msg=True, threads=num_threads)
        else: 
            solver = pulp.PULP_CBC_CMD(msg=True, threads=num_threads)

        model.solve(solver)        
    elif solver == 'copt':
        from pulp import COPT
        solver = COPT()
        model.solve(solver)
    else:
        raise ValueError(f"Unsupported solver: {solver}")
    return model

# TODO: test
def load_solution(params, filename, solver):
    """
    加载解文件并转换为统一的数据结构。
    对于 PuLP 写出的 JSON 格式，变量名格式为 "变量名_索引"
    例如: "d_1_1", "t_start_1_1", "CCT", "t_step_end_1" 等。
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
    检查解是否满足所有约束，与 model_gurobi.py 中 _validate_solution 保持一致
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
        # (1) 消息大小约束：每个步骤 i 内，所有 OCS 的数据量之和应等于 m_i[i]
        sum_d = sum(d[(i, j)] for j in range(1, k + 1))
        if abs(sum_d - m_i[i]) > epsilon:
            log.info(f"步骤 {i} 消息大小约束不满足: sum(d)= {sum_d}, m_i[{i}]= {m_i[i]}")
            return False

        for j in range(1, k + 1):
            # (2) 带宽+时延限制约束：t_end - t_start == d/B + T_lat * u
            expected_duration = d[(i, j)] / B + T_lat * u[(i, j)]
            if abs((t_end[(i, j)] - t_start[(i, j)]) - expected_duration) > epsilon:
                log.info(f"步骤 {i}, OCS {j} 带宽+时延限制不满足: t_end-t_start= {t_end[(i, j)] - t_start[(i, j)]}, expected= {expected_duration}")
                return False

            # (3) 使用指示变量约束：若 d>0，则 u 应为1
            if d[(i, j)] > epsilon and u[(i, j)] < 0.5:
                log.info(f"步骤 {i}, OCS {j} 使用指示变量不一致: d= {d[(i, j)]}, u= {u[(i, j)]}")
                return False

            # (4) 重配置时间约束：t_reconf_end - t_reconf_start == r * T_reconf
            if abs((t_reconf_end[(i, j)] - t_reconf_start[(i, j)]) - r[(i, j)] * T_reconf) > epsilon:
                log.info(f"步骤 {i}, OCS {j} 重配置时间不满足: t_reconf_end-t_reconf_start= {t_reconf_end[(i, j)] - t_reconf_start[(i, j)]}, expected= {r[(i, j)] * T_reconf}")
                return False

            # (5) 传输必须在重配置后开始
            if t_start[(i, j)] < t_reconf_end[(i, j)] - epsilon:
                log.info(f"步骤 {i}, OCS {j} 传输开始早于重配置结束: t_start= {t_start[(i, j)]}, t_reconf_end= {t_reconf_end[(i, j)]}")
                return False

            # (6) 配置变化指示变量：对于非第一步，若配置发生变化且 u=1，则 r 应为1
            if i > 1:
                if configurations[i] != configurations[i - 1] and u[(i, j)] > 0.5 and r[(i, j)] < 0.5:
                    log.info(f"步骤 {i}, OCS {j} 配置变化指示不满足: u= {u[(i, j)]}, r= {r[(i, j)]}")
                    return False

        # (8) 步骤完成时间定义：t_step_end[i] 应等于所有 OCS (t_end * u) 的最大值
        max_val = max(t_end[(i, j)] * u[(i, j)] for j in range(1, k + 1))
        if abs(t_step_end[i] - max_val) > epsilon:
            log.info(f"步骤 {i} 完成时间定义不满足: t_step_end= {t_step_end[i]}, expected= {max_val}")
            return False

        # (9) 步骤依赖性约束：对于 i>1，每个步骤的传输开始时间不早于前一步骤的完成时间
        if i > 1:
            for j in range(1, k + 1):
                if t_start[(i, j)] < t_step_end[i - 1] - epsilon:
                    log.info(f"步骤 {i}, OCS {j} 依赖性不满足: t_start= {t_start[(i, j)]}, 前一步骤完成时间= {t_step_end[i - 1]}")
                    return False

    # (10) 通信完成时间定义：CCT 应大于等于所有步骤完成时间的最大值
    if abs(cct - max(t_step_end[i] for i in range(1, num_steps + 1))) > epsilon:
        log.info(f"CCT 定义不满足: cct= {cct}, expected>= {max(t_step_end[i] for i in range(1, num_steps + 1))}")
        return False

    log.info("所有约束均满足")
    return True

def load_and_validate_solution(params, filename, if_debug_model=False, solver='pulp'):
    """
    加载解文件后验证解的可行性，并输出验证结果
    """
    cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = load_solution(params, filename, solver)
    valid = validate_solution(params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct, if_debug_model)
    model_mode = "调试" if if_debug_model else "正常"
    log.info(f"解在 {model_mode} 模型中是{'可行' if valid else '不可行'}的\n")
    return valid