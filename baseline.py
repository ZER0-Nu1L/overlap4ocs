# baseline.py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def compute_baseline_schedule(params):
    """
    计算基线调度并返回调度信息和通信完成时间 (CCT)。

    Args:
        params (dict): 包含所有必要参数的字典。

    Returns:
        CCT (float): 通信完成时间。
        schedule (list): 调度信息列表。
    """
    # 提取参数
    p = params['p']
    m = params['m']
    k = params['k']
    B = params['B']
    T_reconf = params['T_reconf']
    s = params['s']
    num_steps = params['num_steps']
    configurations = params['configurations']
    m_i = params['m_i']

    # 创建 schedule 列表
    schedule = []

    # 初始化 OCS 的上一次配置和可用时间
    last_config = [None] * k  # 列表，长度为 k，存储每个 OCS 的最后配置编号
    available_time = [0.0] * k  # 列表，长度为 k，存储每个 OCS 的可用时间

    # 遍历每个步骤，计算时间
    for i in range(1, num_steps + 1):
        for j in range(k):
            current_config = configurations[i]
            # 检查是否需要重配置
            if last_config[j] != current_config:
                # 需要重配置
                reconf_needed = 1
                t_reconf_start = available_time[j]
                t_reconf_end = t_reconf_start + T_reconf
            else:
                # 不需要重配置
                reconf_needed = 0
                t_reconf_start = available_time[j]
                t_reconf_end = available_time[j]  # 无需重配置

            # 传输开始时间
            t_trans_start = t_reconf_end
            # 传输结束时间
            trans_time = (m_i[i] / k) / B
            t_trans_end = t_trans_start + trans_time

            # 更新 OCS 的可用时间
            available_time[j] = t_trans_end

            # 更新最后配置
            if reconf_needed:
                last_config[j] = current_config

            # 标记是否被使用
            used = 1 if m_i[i] > 0 else 0

            # 将当前活动添加到 schedule 列表
            schedule.append({
                'step': i,
                'ocs': j + 1,
                'd': m_i[i] / k,
                't_start': t_trans_start,
                't_end': t_trans_end,
                'reconf': reconf_needed,
                't_reconf_start': t_reconf_start,
                't_reconf_end': t_reconf_end,
                'used': used
            })

    # 计算步骤完成时间和通信完成时间
    t_step_end = {}
    for i in range(1, num_steps + 1):
        # 获取所有 OCS 在步骤 i 的传输结束时间
        step_trans_end_times = [s['t_end'] for s in schedule if s['step'] == i and s['used'] == 1]
        if step_trans_end_times:
            t_step_end[i] = max(step_trans_end_times)
        else:
            t_step_end[i] = 0.0

    # 通信完成时间为最后一个步骤的完成时间
    CCT = t_step_end[num_steps]

    # 按开始时间排序 schedule
    schedule.sort(key=lambda s: s['t_start'])

    return CCT, schedule