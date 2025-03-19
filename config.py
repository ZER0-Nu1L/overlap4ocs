# config.py
import logging as log

def get_parameters():
    # 输入参数
    params = {}

    # 1. 拓扑
    params['k'] = 4  # OCS 数量
    # params['B'] = 400 * 1024 * 1024 / 8  # 带宽，400Gbps，转换为字节/ms
    params['B'] = 800 * 1024 * 1024 / 8 / params['k']  # 带宽，400Gbps，转换为字节/ms
    params['T_reconf'] = 2  # 重配置时间，2毫秒

    # 2. CC
    params['p'] = 16  # 计算节点数量
    params['m'] = 600 * 1024 * 1024  # 总消息大小，400MB，转换为字节

    # 3. 算法选择
    params['algorithm'] = 'a2a_pairwise'
    # 可选: 'ar_having-doubling', 'a2a_pairwise', 'a2a_bruck'

    # 4. 算法特定参数计算
    algorithm = params['algorithm']
    match algorithm:
        case 'a2a_bruck':
            params.update(compute_a2a_bruck_params(params['p'], params['m']))
        case 'a2a_pairwise':
            params.update(compute_a2a_pairwise_params(params['p'], params['m']))
        case 'ar_having-doubling':
            params.update(compute_having_doubling_params(params['p'], params['m']))
        case 'ring':
            params.update(compute_ring_params(params['p'], params['m']))
        case 'binary-tree':
            params.update(compute_binary_tree_params(params['p'], params['m']))
        case _:
            raise ValueError(f"不支持的算法: {algorithm}")

    log.info(params)
    return params

## Having Doubling（Rabenseifner's Algorithm）
def compute_having_doubling_params(p, m):
    p_new = 2 ** ((p).bit_length() - 1)  # NOTE: 小于等于 p 的最大 2 的幂次方数
    s = (p_new - 1).bit_length()         # NOTE: (p - 1).bit_length() 即 ceil(log2(p))
    
    num_steps = 2 * s
    return {
        'p': p_new, # FIXME: 暂时这么处理
        's': s,
        'num_steps': num_steps,
        'm_i': compute_hd_message_sizes(m, s, num_steps),
        'configurations': compute_hd_configurations(s, num_steps)
    }

def compute_hd_message_sizes(m, s, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        if i <= s:
            m_i[i] = m / (2 ** i)
        else:
            m_i[i] = m_i[2 * s + 1 - i]
    return m_i

def compute_hd_configurations(s, num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = min(i, 2 * s - i + 1)
    return configurations

## All-to-all（Pairwise Exchange）
def compute_a2a_pairwise_params(p, m):
    num_steps = p - 1
    return {
        'p': p, # FIXME: 暂时这么处理
        'num_steps': num_steps,
        'm_i': compute_a2a_pairwise_message_sizes(m, num_steps),
        'configurations': compute_a2a_pairwise_configurations(num_steps)
    }

def compute_a2a_pairwise_message_sizes(m, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m / num_steps
    return m_i    

def compute_a2a_pairwise_configurations(num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations

## All-to-all（Bruck）
def compute_a2a_bruck_params(p, m):
    p_new = 2 ** ((p).bit_length() - 1)  # NOTE: 小于等于 p 的最大 2 的幂次方数
    s = (p_new - 1).bit_length()         # NOTE: (p - 1).bit_length() 即 ceil(log2(p))
    
    num_steps = s
    return {
        'p': p_new, # FIXME: 暂时这么处理
        's': s,
        'num_steps': num_steps,
        'm_i': compute_a2a_bruck_message_sizes(m, num_steps),
        'configurations': compute_a2a_bruck_configurations(num_steps)
    }

def compute_a2a_bruck_message_sizes(m, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m
    return m_i    

def compute_a2a_bruck_configurations(num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations