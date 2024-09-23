# config.py
import numpy as np


def get_parameters():
    # 输入参数
    params = {}

    # 1. 拓扑
    params['k'] = 3  # OCS 数量
    params['B'] = 400 * 1024 * 1024 / 8  # 带宽，400Gbps，转换为字节/秒
    params['T_reconf'] = 2  # 重配置时间，2秒

    # 2. CC
    params['p'] = 8  # 计算节点数量
    params['m'] = 400 * 1024 * 1024  # 总消息大小，400MB，转换为字节
    params['s'] = int(np.log2(params['p']))  # HD 算法的步骤数

    # 3. Having-Doubling 算法计算
    params['num_steps'] = 2 * params['s']
    params['m_i'] = compute_message_sizes(params['m'], params['s'], params['num_steps'])
    params['configurations'] = compute_configurations(params['s'], params['num_steps'])

    return params


def compute_message_sizes(m, s, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        if i <= s:
            m_i[i] = m / (2 ** i)
        else:
            m_i[i] = m_i[2 * s + 1 - i]
    return m_i


def compute_configurations(s, num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = min(i, 2 * s - i + 1)
    return configurations
