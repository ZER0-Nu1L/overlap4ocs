# main.py
from config import get_parameters
from model import build_model, optimize_model
from baseline import compute_baseline_schedule
from scheduler_analysis import extract_results, plot_schedule


def main():
    # 获取参数
    params = get_parameters()
    # 构建模型
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)
    # 优化模型
    model = optimize_model(model)

    # 提取并显示结果
    schedule = extract_results(model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, params)

    # Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)

    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=True,
                  filename='figures/optimized_schedule.pdf')
    plot_schedule(schedule_baseline, params['k'], params['T_reconf'], save_as_pdf=True,
                  filename='figures/baseline_schedule.pdf')

    # 显示基线结果
    print(f"\nBaseline CCT: {cct_baseline * 1000:.2f} ms")
    for s in schedule_baseline:
        print(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d'] / (1024 * 1024):.2f} MB, "
              f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
              f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")

    # 比较优化结果和基线结果
    print("\nComparison:")
    print(f"Optimized CCT: {cct.X * 1000:.2f} ms")
    print(f"Baseline CCT: {cct_baseline * 1000:.2f} ms")
    improvement = ((cct_baseline - cct.X) / cct_baseline) * 100 if cct_baseline != 0 else 0
    print(f"Improvement: {improvement:.2f}%")


if __name__ == "__main__":
    main()
