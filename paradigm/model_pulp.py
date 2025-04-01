import pulp
import os, json
import logging as log

def build_model(params, debug_model=False):
    """
    构建基于 PuLP 的 MILP 模型，返回模型以及决策变量字典：
    CCT, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end
    """
    num_steps = params['num_steps']
    k = params['k']
    B = params['B']
    T_reconf = params['T_reconf']
    m_i = params['m_i']
    configurations = params['configurations']
    M = params['m']  # 用于消息大小约束的大 M
    # 定义一个用于时间变量线性化的大 M（需足够大）
    M_time = 1e6

    # 创建字典存储变量
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

    # 若非 debug 模式，则需要引入辅助变量对 bilinear 项进行线性化
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

    # 创建 PuLP 问题
    prob = pulp.LpProblem("Optimization_with_overlapping_tech", pulp.LpMinimize)
    prob += CCT, "Minimize_CCT"

    # (1) 消息大小约束：每个步骤 i 内，所有 OCS 上传的数据量之和等于 m_i[i]
    for i in range(1, num_steps+1):
        prob += (pulp.lpSum(d[(i,j)] for j in range(1, k+1)) == m_i[i],
                 f"msg_size_step_{i}")

    # (2) 带宽限制约束：t_end - t_start == d/B
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_end[(i,j)] - t_start[(i,j)] == (1.0 / B) * d[(i,j)],
                     f"bandwidth_step_{i}_{j}")

    # (3) 使用指示变量约束：若 u 为 0，则 d 必须为 0
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (d[(i,j)] <= u[(i,j)] * M, f"use_indicator_step_{i}_{j}")
            # d 的非负性由 lowBound=0 保证

    # (4) 重配置时间约束：t_reconf_end - t_reconf_start == r * T_reconf
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_reconf_end[(i,j)] - t_reconf_start[(i,j)] == r[(i,j)] * T_reconf,
                     f"reconf_time_step_{i}_{j}")

    # (5) 传输与重配置依赖：传输开始必须在重配置结束之后
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            prob += (t_start[(i,j)] >= t_reconf_end[(i,j)],
                     f"trans_after_reconf_step_{i}_{j}")

    # (6) 配置变化指示变量：
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            if i == 1:
                prob += (r[(i,j)] >= u[(i,j)], f"r_initial_step_{i}_{j}")
            else:
                # 若 configurations[i] 与 configurations[i-1] 相同，则 same_config 取 1，否则为 0
                same_config = 1 if configurations[i] == configurations[i-1] else 0
                prob += (r[(i,j)] >= u[(i,j)] - same_config, f"r_def_step_{i}_{j}")
            prob += (u[(i,j)] >= r[(i,j)], f"u_after_r_{i}_{j}")

    # (7) OCS 活动时间不重叠约束
    if debug_model:
        # debug 模型下直接使用原始变量
        for j in range(1, k+1):
            for i in range(2, num_steps+1):
                prob += (t_reconf_start[(i,j)] >= t_end[(i-1,j)],
                         f"reconf_after_prev_end_step_{i}_{j}")
                prob += (t_reconf_start[(i,j)] >= t_reconf_start[(i-1,j)],
                         f"reconf_after_prev_reconf_step_{i}_{j}")
    else:
        # 非 debug 模型下使用辅助变量 t_prev_end, 并对 bilinear 项进行线性化
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

        # 对 bilinear 项线性化
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

    # (8) 步骤完成时间定义：每个步骤 i 的完成时间不小于所有 OCS 的“传输结束时间 × u”——若使用线性化则用 v
    for i in range(1, num_steps+1):
        for j in range(1, k+1):
            if debug_model:
                # 为避免 bilinear 项，这里直接使用 t_end（假设 debug 下 u 取1的情况较多）
                prob += (t_step_end[i] >= t_end[(i,j)],
                         f"step_end_step_{i}_{j}")
            else:
                prob += (t_step_end[i] >= v[(i,j)],
                         f"step_end_step_{i}_{j}")

    # (9) 步骤依赖性约束：后一步骤的传输开始时间不早于前一步骤完成时间
    for i in range(2, num_steps+1):
        for j in range(1, k+1):
            prob += (t_start[(i,j)] >= t_step_end[i-1],
                     f"trans_after_prev_step_end_step_{i}_{j}")

    # (10) 通信完成时间定义：CCT 至少等于每个步骤的完成时间
    for i in range(1, num_steps+1):
        prob += (CCT >= t_step_end[i], f"CCT_def_step_{i}")

    # 返回模型与决策变量（辅助变量仅在内部使用，不在外部返回）
    return prob, CCT, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end