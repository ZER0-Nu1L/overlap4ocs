# optimizer.py
from gurobipy import GRB
import matplotlib.pyplot as plt
import matplotlib.patches as patches


def extract_results(model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, params):
    if model.status == GRB.OPTIMAL:
        print(f"Optimal CCT: {cct.X * 1000:.2f} ms")
        schedule = []
        k = params['k']
        num_steps = params['num_steps']

        for i in range(1, num_steps + 1):
            for j in range(k):
                schedule.append({
                    'step': i,
                    'ocs': j + 1,
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
        for s in schedule:
            print(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d']}, "
                  f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
                  f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")
        return schedule
    else:
        print("No optimal solution found.")
        return None


def plot_schedule(schedule, num_ocs, T_reconf, save_as_pdf=False, filename='schedule.pdf'):
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
        for s in ocs_schedule:
            # 绘制重配置阶段
            if s['reconf'] > 0.5:
                ax.barh(
                    y,
                    s['t_reconf_end'] - s['t_reconf_start'],
                    left=s['t_reconf_start'],
                    height=0.8,
                    color=colors['reconfiguration'],
                    edgecolor=colors['reconfiguration_edge_color']
                )
                ax.text(
                    s['t_reconf_start'] + (s['t_reconf_end'] - s['t_reconf_start']) / 2,
                    y,
                    "Reconf",
                    ha='center',
                    va='center',
                    color='black',
                    fontsize=10,
                    fontweight='normal'
                )
            # 绘制传输阶段
            if s['used'] > 0.5 and s['d'] > 0:
                ax.barh(
                    y,
                    s['t_end'] - s['t_start'],
                    left=s['t_start'],
                    height=0.8,
                    color=colors['transmission'],
                    edgecolor=colors['transmission_edge_color']
                )
                ax.text(
                    s['t_start'] + (s['t_end'] - s['t_start']) / 2,
                    y,
                    f"Step {s['step']}",
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

    # 显示图表
    plt.show()
