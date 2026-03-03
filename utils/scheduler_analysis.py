# optimizer.py
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import logging as log


def extract_results(source, **kwargs):
    """Universal result extraction function"""
    def get_value(var):
        return var.X if hasattr(var, 'X') else var.varValue

    T_lat = kwargs.get('params', {}).get('T_lat', 0)

    if isinstance(source, list):  # NOTE: for "processors" model
        schedule = []
        for processor in source:
            for task_name, start_time, finish_time in processor.tasks:
                schedule.append({
                    'step': int(task_name.replace('Step', '')) if 'Step' in task_name else 0,
                    'ocs': processor.name.replace('P', ''),
                    'used': 1,
                    'd': 1,  # For simplicity
                    't_start': start_time,
                    't_end': finish_time,
                    'reconf': 0,
                    't_reconf_start': start_time,
                    't_reconf_end': start_time,
                    't_lat': T_lat
                })
        schedule.sort(key=lambda s: s['t_start'])
        return schedule
    else:
        model = source
        cct = kwargs['cct']
        d = kwargs['d']
        t_start = kwargs['t_start']
        t_end = kwargs['t_end']
        u = kwargs['u']
        r = kwargs['r']
        t_reconf_start = kwargs['t_reconf_start']
        t_reconf_end = kwargs['t_reconf_end']
        t_step_end = kwargs['t_step_end']
        params = kwargs['params']
        k = params['k']
        num_steps = params['num_steps']
        solver = params['solver']

        if solver == 'gurobi':
            from gurobipy import GRB
            optimal = (model.status == GRB.OPTIMAL)
        elif params['solver'] == 'pulp' or params['solver'] == 'copt' or params['solver'] == 'pulp_gurobi':
            import pulp
            status_str = pulp.LpStatus[model.status]
            log.info("Pulp solver status: %s", status_str)
            optimal = (status_str == 'Optimal')

        if optimal:
            schedule = []
            for i in range(1, num_steps + 1):
                for j in range(1, k + 1):
                    is_used = get_value(u[(i, j)])
                    schedule.append({
                        'step': i,
                        'ocs': j,
                        'd': get_value(d[(i, j)]),
                        't_start': get_value(t_start[(i, j)]),
                        't_end': get_value(t_end[(i, j)]),
                        'reconf': get_value(r[(i, j)]),
                        't_reconf_start': get_value(t_reconf_start[(i, j)]),
                        't_reconf_end': get_value(t_reconf_end[(i, j)]),
                        'used': is_used,
                        't_lat': T_lat if is_used > 0.5 else 0.0
                    })
            schedule.sort(key=lambda s: s['t_start'])
            return schedule
        else:
            log.info("No optimal solution found.")
            return None


def apply_offset(schedule_item, offset):
    """Apply time offset to a single scheduling item"""
    return {
        **schedule_item,
        't_start': schedule_item['t_start'] - offset,
        't_end': schedule_item['t_end'] - offset,
        't_reconf_start': schedule_item['t_reconf_start'] - offset,
        't_reconf_end': schedule_item['t_reconf_end'] - offset,
        't_lat': schedule_item.get('t_lat', 0.0)
    }

def plot_schedule(schedule, num_ocs, T_reconf, save_as_pdf=False, filename='schedule.pdf', show=False):
    # Function implementation
    # Define colors and styles
    colors = {
        'transmission': '#dde8fa',  # Blue
        'transmission_edge_color': '#738dbb',
        'latency': '#ffdce5',  # Pink for latency slot
        'latency_edge_color': '#d58b9f',
        'reconfiguration': '#fdf2d0',  # Orange
        'reconfiguration_edge_color': '#d1b765',
        'idle': '#DDDDDD',  # Light gray (unused)
        'edge_color': 'black'
    }
    # Create the plot object
    fig, ax = plt.subplots(figsize=(12, 6))
    # Set font and font size
    plt.rcParams.update({'font.size': 12})
    
    for ocs in range(1, num_ocs + 1):
        y = num_ocs - ocs  # OCS numbers are arranged from top to bottom
        ocs_schedule = [s for s in schedule if s['ocs'] == ocs]
        # log.info(f"OCS {ocs} schedule: {ocs_schedule}")
        offset = T_reconf  # NOTE: Offset to treat the first reconfiguration as system startup time, not included in CCT
        for s in ocs_schedule:
            s_offset = apply_offset(s, offset)
            
            # Plot the reconfiguration phase
            if s_offset['reconf'] > 0.5:
                ax.barh(
                    y,
                    s_offset['t_reconf_end'] - s_offset['t_reconf_start'],
                    left=s_offset['t_reconf_start'],
                    height=0.8,
                    color=colors['reconfiguration'],
                    edgecolor=colors['reconfiguration_edge_color']
                )
                ax.text(
                    s_offset['t_reconf_start'] + (s_offset['t_reconf_end'] - s_offset['t_reconf_start']) / 2,
                    y,
                    "Reconf",
                    ha='center',
                    va='center',
                    color='black',
                    fontsize=10,
                    fontweight='normal'
                )
            # Plot the latency + transmission phases
            if s_offset['used'] > 0.5 and s_offset['d'] > 0:
                total_duration = s_offset['t_end'] - s_offset['t_start']
                latency_duration = min(max(s_offset.get('t_lat', 0.0), 0.0), max(total_duration, 0.0))
                payload_duration = max(total_duration - latency_duration, 0.0)

                if latency_duration > 0:
                    ax.barh(
                        y,
                        latency_duration,
                        left=s_offset['t_start'],
                        height=0.8,
                        color=colors['latency'],
                        edgecolor=colors['latency_edge_color']
                    )

                if payload_duration > 0:
                    ax.barh(
                        y,
                        payload_duration,
                        left=s_offset['t_start'] + latency_duration,
                        height=0.8,
                        color=colors['transmission'],
                        edgecolor=colors['transmission_edge_color']
                    )

                text_center = s_offset['t_start'] + latency_duration + (payload_duration / 2 if payload_duration > 0 else latency_duration / 2)
                ax.text(
                    text_center,
                    y,
                    f"Step {s_offset['step']}",
                    ha='center',
                    va='center',
                    color='black',
                    fontsize=10,
                    fontweight='normal'
                )

    # Set y-axis ticks and labels
    ax.set_yticks(range(num_ocs))
    ax.set_yticklabels([f"OCS {i}" for i in range(num_ocs, 0, -1)])
    ax.set_ylim(-0.5, num_ocs - 0.5)  # Adjust y-axis range

    # Set x-axis label, title, and grid
    ax.set_xlabel("Time (ms)")
    ax.set_title("Optimized Transmission and Reconfiguration Schedule")
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)

    # Add legend
    reconf_patch = patches.Patch(color=colors['reconfiguration'], label='Reconfiguration')
    latency_patch = patches.Patch(color=colors['latency'], label='Latency overhead')
    trans_patch = patches.Patch(color=colors['transmission'], label='Payload transmission')
    ax.legend(handles=[reconf_patch, latency_patch, trans_patch], loc='upper right')

    # Adjust layout
    plt.tight_layout()

    # Save as PDF (if needed)
    if save_as_pdf:
        plt.savefig(filename, format='pdf', bbox_inches='tight')

    if show:
        # Display the chart
        plt.show()
