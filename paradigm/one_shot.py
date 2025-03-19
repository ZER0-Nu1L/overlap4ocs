# oneshot.py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def compute_oneshot_schedule(params):
    # 1. 判断 distinct configurations 的数量 是否 小于等于 k = params['k']；
    # 如果小于等于则继续，如果大于则函数返回 none
    k = params['k']
    configurations = params['configurations']
    
    distinct_configs_num = len(set(configurations.values()))
    
    # 如果不同配置数量大于k，返回None
    if distinct_configs_num > k:
        return None, []
    
    # FIXME: 可能会产生不公平
    # 我们现在希望 distinct configurations 的数量 和 k 是倍数关系；
    # 现在的不公平方式是增强 one-shot
    
    # 1. 计算 k 是 distinct_configs_num 的几倍
    d = int(np.ceil(k / distinct_configs_num))
    
    # 创建 schedule 列表和步骤完成时间字典
    schedule = []
    t_step_end = {0: 0.0}  # 初始化步骤0的完成时间为0
    
    # 提取必要参数
    B = params['B']
    m_i = params['m_i']
    num_steps = params['num_steps']
    
    # 首先为每个OCS添加一次重配置
    T_reconf = params['T_reconf']
    for j in range(1, k + 1):
        schedule.append({
            'step': 0,
            'ocs': j,
            'd': 0,
            't_start': 0,
            't_end': 0,
            'reconf': 1,  # 需要重配置
            't_reconf_start': 0,
            't_reconf_end': T_reconf,
            'used': 0
        })
    
    # 更新步骤0的完成时间为重配置时间
    t_step_end[0] = T_reconf
    
    # 遍历每个步骤
    for i in range(1, num_steps + 1):
        current_config = configurations[i]
        trans_time = (m_i[i]) / B / d
        t_trans_start = t_step_end[i-1]
        t_trans_end = t_trans_start + trans_time
        
        # 为当前配置分配的OCS范围
        start_ocs = (current_config - 1) * d + 1
        end_ocs = min(current_config * d, k) + 1
        
        # 为每个分配的OCS创建调度
        for j in range(start_ocs, end_ocs):
            schedule.append({
                'step': i,
                'ocs': j,
                'd': m_i[i] / k,
                't_start': t_trans_start,
                't_end': t_trans_end,
                'reconf': 0,  # 不需要重配置
                't_reconf_start': t_trans_start,
                't_reconf_end': t_trans_start,
                'used': 1 if m_i[i] > 0 else 0
            })
        
        # 更新当前步骤的完成时间
        t_step_end[i] = t_trans_end
    
    # 通信完成时间为最后一个步骤的完成时间
    CCT = t_step_end[num_steps]
    
    # 按开始时间排序 schedule
    schedule.sort(key=lambda s: s['t_start'])
    
    return CCT, schedule