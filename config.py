# config.py
import logging as log


def get_parameters():
    # 输入参数
    params = {}

    # 1. 拓扑
    params['k'] = 2  # OCS 数量
    params['B'] = 400 * 1024 * 1024 / 8  # 带宽，400Gbps，转换为字节/秒
    params['T_reconf'] = 2  # 重配置时间，2秒

    # 2. CC
    params['p'] = 10  # 计算节点数量
    params['m'] = 400 * 1024 * 1024  # 总消息大小，400MB，转换为字节

    # 3. 算法选择
    params['algorithm'] = 'having-doubling'  # 可选: 'having-doubling', 'ring', 'binary-tree'等

    # 4. 算法特定参数计算
    algorithm = params['algorithm']
    match algorithm:
        case 'having-doubling':
            params.update(compute_having_doubling_params(params['p'], params['m']))
        case 'ring':
            params.update(compute_ring_params(params['p'], params['m']))
        case 'binary-tree':
            params.update(compute_binary_tree_params(params['p'], params['m']))
        case _:
            raise ValueError(f"不支持的算法: {algorithm}")

    log.info(params)
    return params


def compute_having_doubling_params(p, m):
    p_new = 2 ** ((p - 1).bit_length() - 1)
    s = (p_new - 1).bit_length() # NOTE: (p - 1).bit_length() 即 ceil(log2(p))
    
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


# NOTE: 更多接口实现

def compute_ring_params(p, m):
    num_steps = p - 1
    return {
        'num_steps': num_steps,
        'm_i': {i: m / p for i in range(1, num_steps + 1)},
        'configurations': {i: 1 for i in range(1, num_steps + 1)}
    }

def compute_binary_tree_params(p, m):
    depth =  (p - 1).bit_length() # 即 int(np.ceil(np.log2(p)))
    num_steps = 2 * depth - 1
    return {
        'depth': depth,
        'num_steps': num_steps,
        'm_i': compute_bt_message_sizes(m, depth, num_steps),
        'configurations': compute_bt_configurations(depth, num_steps)
    }

def compute_bt_message_sizes(m, depth, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        if i <= depth:
            m_i[i] = m / (2 ** i)
        else:
            m_i[i] = m / (2 ** (num_steps - i + 1))
    return m_i

def compute_bt_configurations(depth, num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        if i <= depth:
            configurations[i] = i
        else:
            configurations[i] = num_steps - i + 1
    return configurations
