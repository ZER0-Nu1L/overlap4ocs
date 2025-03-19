# optimizer.py
from gurobipy import GRB
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import logging as log


def extract_results(source, **kwargs):
    """通用的结果提取函数
    
    Args:
        source: 可以是 model 对象或 processors 列表
        **kwargs: 不同来源需要的额外参数
            - 对于 model: cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, params
            - 对于 processors: makespan
    
    Returns:
        schedule: 标准格式的调度结果列表
    """
    if isinstance(source, list):  # processors 列表
        # DAG 调度结果格式转换
        schedule = []
        for processor in source:
            for task_name, start_time, finish_time in processor.tasks:
                schedule.append({
                    'step': int(task_name.replace('Step', '')) if 'Step' in task_name else 0,
                    'ocs': processor.name.replace('P', ''),  # 将 'P1' 转换为 '1'
                    'used': 1,
                    'd': 1,  # 简化处理，实际可从 task weight 计算
                    't_start': start_time,
                    't_end': finish_time,
                    'reconf': 0,  # 由于 DAG 中的 comm_cost 已经包含在调度中
                    't_reconf_start': start_time,  # 简化处理
                    't_reconf_end': start_time     # 简化处理
                })
        # 按开始时间排序
        schedule.sort(key=lambda s: s['t_start'])
        # 输出调度结果
        log.info("-----------------------------------")
        log.info("schedule sorted by start time")
        log.info("-----------------------------------")
        for s in schedule:
            log.info(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d']}, "
                f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
                f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")
        return schedule
    
    else:  # Gurobi model
        # 原有的 model 结果提取逻辑
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
        
        if model.status == GRB.OPTIMAL:
            schedule = []
            k = params['k']
            num_steps = params['num_steps']

            for i in range(1, num_steps + 1):
                for j in range(1, k+1):
                    schedule.append({
                        'step': i,
                        'ocs': j,
                        'd': d[i, j].X,
                        't_start': t_start[i, j].X,
                        't_end': t_end[i, j].X,
                        'reconf': r[i, j].X,
                        't_reconf_start': t_reconf_start[i, j].X,
                        't_reconf_end': t_reconf_end[i, j].X,
                        'used': u[i, j].X
                    })
            # 按开始时间排序
            schedule.sort(key=lambda s: s['t_start'])
            # 输出调度结果
            log.info("-----------------------------------")
            log.info("schedule sorted by start time")
            log.info("-----------------------------------")
            for s in schedule:
                log.info(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d']}, "
                    f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
                    f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")
            # log.info("-----------------------------------")
            # log.info("schedule sorted by OCS")
            # log.info("-----------------------------------")
            # for s in sorted(schedule, key=lambda x: x['ocs']):
            #     log.info(f"OCS {s['ocs']}, Step {s['step']}, Used: {s['used']}, Data: {s['d']}, "
            #           f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
            #           f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")
            return schedule
        else:
            log.info("No optimal solution found.")
            # return schedule
            return None


def apply_offset(schedule_item, offset):
    """对单个调度项应用时间偏移"""
    return {
        **schedule_item,
        't_start': schedule_item['t_start'] - offset,
        't_end': schedule_item['t_end'] - offset,
        't_reconf_start': schedule_item['t_reconf_start'] - offset,
        't_reconf_end': schedule_item['t_reconf_end'] - offset
    }

def plot_schedule(schedule, num_ocs, T_reconf, save_as_pdf=False, filename='schedule.pdf', show=False):
    # 函数实现# 定义颜色和样式
    colors = {
        'transmission': '#dde8fa',  # 蓝色
        'transmission_edge_color': '#738dbb',
        'reconfiguration': '#fdf2d0',  # 橙色
        'reconfiguration_edge_color': '#d1b765',
        'idle': '#DDDDDD',  # 浅灰色（未使用）
        'edge_color': 'black'
    }
    # 创建绘图对象
    fig, ax = plt.subplots(figsize=(12, 6))
    # 设置字体和字号
    plt.rcParams.update({'font.size': 12})
    
    for ocs in range(1, num_ocs + 1):
        y = num_ocs - ocs  # OCS 编号从上到下排列
        ocs_schedule = [s for s in schedule if s['ocs'] == ocs]
        # log.info(f"OCS {ocs} schedule: {ocs_schedule}")
        offset = T_reconf # NOTE: 偏移量，使得第一次重配置作为系统启动时间，不计入CCT
        for s in ocs_schedule:
            s_offset = apply_offset(s, offset)
            
            # 绘制重配置阶段
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
            # 绘制传输阶段
            if s_offset['used'] > 0.5 and s_offset['d'] > 0:
                ax.barh(
                    y,
                    s_offset['t_end'] - s_offset['t_start'],
                    left=s_offset['t_start'],
                    height=0.8,
                    color=colors['transmission'],
                    edgecolor=colors['transmission_edge_color']
                )
                ax.text(
                    s_offset['t_start'] + (s_offset['t_end'] - s_offset['t_start']) / 2,
                    y,
                    f"Step {s_offset['step']}",
                    ha='center',
                    va='center',
                    color='black',
                    fontsize=10,
                    fontweight='normal'
                )

    # 设置 y 轴刻度和标签
    ax.set_yticks(range(num_ocs))
    ax.set_yticklabels([f"OCS {i}" for i in range(num_ocs, 0, -1)])
    ax.set_ylim(-0.5, num_ocs - 0.5)  # 调整 y 轴范围

    # 设置 x 轴标签、标题和网格
    ax.set_xlabel("Time (s)")
    ax.set_title("Optimized Transmission and Reconfiguration Schedule")
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)

    # 添加图例
    reconf_patch = patches.Patch(color=colors['reconfiguration'], label='Reconfiguration')
    trans_patch = patches.Patch(color=colors['transmission'], label='Transmission')
    ax.legend(handles=[reconf_patch, trans_patch], loc='upper right')

    # 调整布局
    plt.tight_layout()

    # 保存为 PDF（如果需要）
    if save_as_pdf:
        plt.savefig(filename, format='pdf', bbox_inches='tight')

    if show:
        # 显示图表
        plt.show()
