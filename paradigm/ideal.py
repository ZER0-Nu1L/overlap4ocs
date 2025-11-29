
def compute_ideal_time(params):
    B = params['B']
    k = params['k']
    m_i = params['m_i']
    num_steps = params['num_steps']
    T_lat = params.get('T_lat', 0)
    CCT = sum((m_i[i] / (B * k)) + T_lat for i in range(1, num_steps + 1))
    # B * k stands for the total bandwidth of a single node
    return CCT