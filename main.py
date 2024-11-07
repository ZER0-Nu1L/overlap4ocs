# main.py
from config import get_parameters
from model import build_model, optimize_model, validate_solution
from baseline import compute_baseline_schedule
from scheduler_analysis import extract_results, plot_schedule
import logging as log


def main():    
    # 获取参数
    params = get_parameters()
    # 构建模型
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)
    # 优化模型
    model = optimize_model(model)
    # 验证解的可行性
    is_valid = validate_solution(model, params, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, cct)
    if is_valid:
        log.info("解是可行的")
    else:
        log.info("解不可行")
    
    # 提取并显示结果
    schedule = extract_results(model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end, params)
    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=True,
                  filename='figures/optimized_schedule.pdf')

    # Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
    plot_schedule(schedule_baseline, params['k'], params['T_reconf'], save_as_pdf=True,
                  filename='figures/baseline_schedule.pdf')

    # 显示基线结果
    log.info(f"\nBaseline CCT: {cct_baseline * 1000:.2f} ms")
    for s in schedule_baseline:
        log.info(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d'] / (1024 * 1024):.2f} MB, "
              f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
              f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")

    # 比较优化结果和基线结果
    log.info("Comparison:")
    cct_optimized = cct.X - params['T_reconf']
    cct_baseline = cct_baseline - params['T_reconf']
    log.info(f"Optimized CCT: {(cct_optimized) * 1000:.2f} ms")
    log.info(f"Baseline CCT: {cct_baseline * 1000:.2f} ms")
    improvement = ((cct_baseline - cct_optimized) / cct_baseline) * 100 if cct_baseline != 0 else 0
    log.info(f"Improvement: {improvement:.2f}%")


if __name__ == "__main__":
    # log.basicConfig(level=log.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    log.basicConfig(level=log.INFO, format='%(message)s')

    main()