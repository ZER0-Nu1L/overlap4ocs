import math

def compute_oneshot_schedule(params):
    # 1. Check if the number of distinct configurations is less than or equal to k = params['k'];
    # If it is less than or equal, continue; if it is greater, return None
    k = params['k']
    configurations = params['configurations']
    
    distinct_configs_num = len(set(configurations.values()))
    
    # If the number of distinct configurations is greater than k, return None
    if distinct_configs_num > k:
        return None, []
    
    # NOTE: This may cause unfairness
    # We now want the number of distinct configurations and k to have a multiple relationship;
    # The current unfair approach tends to favor enhancing one-shot
    
    # 2. Calculate how many times k is a multiple of distinct_configs_num
    d = math.ceil(k / distinct_configs_num)
    
    # Create a schedule list and a dictionary for step completion times
    schedule = []
    t_step_end = {0: 0.0}  # Initialize the completion time of step 0 to 0
    
    # Extract necessary parameters
    B = params['B']
    m_i = params['m_i']
    num_steps = params['num_steps']
    
    # First, add one reconfiguration for each OCS
    T_reconf = params['T_reconf']
    for j in range(1, k + 1):
        schedule.append({
            'step': 0,
            'ocs': j,
            'd': 0,
            't_start': 0,
            't_end': 0,
            'reconf': 1,  # Requires reconfiguration
            't_reconf_start': 0,
            't_reconf_end': T_reconf,
            'used': 0
        })
    
    # Update the completion time of step 0 to the reconfiguration time
    t_step_end[0] = T_reconf
    
    # Iterate through each step
    for i in range(1, num_steps + 1):
        current_config = configurations[i]
        trans_time = (m_i[i]) / B / d
        t_trans_start = t_step_end[i-1]
        t_trans_end = t_trans_start + trans_time
        
        # OCS range allocated for the current configuration
        start_ocs = (current_config - 1) * d + 1
        end_ocs = min(current_config * d, k) + 1
        
        # Create a schedule for each allocated OCS
        for j in range(start_ocs, end_ocs):
            schedule.append({
                'step': i,
                'ocs': j,
                'd': m_i[i] / k,
                't_start': t_trans_start,
                't_end': t_trans_end,
                'reconf': 0,  # No reconfiguration required
                't_reconf_start': t_trans_start,
                't_reconf_end': t_trans_start,
                'used': 1 if m_i[i] > 0 else 0
            })
        
        # Update the completion time of the current step
        t_step_end[i] = t_trans_end
    
    # Communication completion time is the completion time of the last step
    CCT = t_step_end[num_steps]
    
    # Sort the schedule by start time
    schedule.sort(key=lambda s: s['t_start'])
    
    return CCT, schedule