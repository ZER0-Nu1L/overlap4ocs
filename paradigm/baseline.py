
def compute_baseline_schedule(params):
    k = params['k']
    B = params['B']
    T_reconf = params['T_reconf']
    num_steps = params['num_steps']
    configurations = params['configurations']
    m_i = params['m_i']

    # Create a schedule list
    schedule = []

    # Initialize the last configuration and available time for each OCS
    last_config = [None] * (k+1)  # List of length k, storing the last configuration number for each OCS
    available_time = [0.0] * (k+1)  # List of length k, storing the available time for each OCS

    # Iterate through each step to calculate time
    for i in range(1, num_steps + 1):
        for j in range(1, k+1):
            current_config = configurations[i]
            # Check if reconfiguration is needed
            if last_config[j] != current_config:
                # Reconfiguration is needed
                reconf_needed = 1
                t_reconf_start = available_time[j]
                t_reconf_end = t_reconf_start + T_reconf
            else:
                # No reconfiguration needed
                reconf_needed = 0
                t_reconf_start = available_time[j]
                t_reconf_end = available_time[j]  # No reconfiguration needed

            # Transmission start time
            t_trans_start = t_reconf_end
            # Transmission end time
            trans_time = (m_i[i] / k) / B
            t_trans_end = t_trans_start + trans_time

            # Update the available time for the OCS
            available_time[j] = t_trans_end

            # Update the last configuration
            if reconf_needed:
                last_config[j] = current_config

            # Mark whether it is used
            used = 1 if m_i[i] > 0 else 0

            # Add the current activity to the schedule list
            schedule.append({
                'step': i,
                'ocs': j,
                'd': m_i[i] / k,
                't_start': t_trans_start,
                't_end': t_trans_end,
                'reconf': reconf_needed,
                't_reconf_start': t_reconf_start,
                't_reconf_end': t_reconf_end,
                'used': used
            })

    # Calculate step completion time and communication completion time
    t_step_end = {}
    for i in range(1, num_steps + 1):
        # Get all OCS transmission end times for step i
        step_trans_end_times = [s['t_end'] for s in schedule if s['step'] == i and s['used'] == 1]
        if step_trans_end_times:
            t_step_end[i] = max(step_trans_end_times)
        else:
            t_step_end[i] = 0.0

    # Communication completion time is the completion time of the last step
    CCT = t_step_end[num_steps]

    # Sort the schedule by start time
    schedule.sort(key=lambda s: s['t_start'])

    return CCT, schedule