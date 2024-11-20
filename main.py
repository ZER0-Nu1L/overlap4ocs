from config import get_parameters
from model import build_model, optimize_model, load_and_validate_solution
from baseline import compute_baseline_schedule
from scheduler_analysis import extract_results, plot_schedule
import logging as log

def main():    
    # 获取参数
    params = get_parameters()
    # .sol or .json
    solution_figure          =  f"figures/origin_solution_k={params['k']}_p={params['p']}.pdf"
    solution_file            = f"solution/origin_solution_k={params['k']}_p={params['p']}.json"
    baseline_figure          =  f"figures/baseline_k={params['k']}_p={params['p']}.pdf"
    baseline_file            = f"solution/baseline_k={params['k']}_p={params['p']}.json"
    debug_solution_figure    =  f"figures/debug_solution_k={params['k']}_p={params['p']}.pdf"
    debug_solution_file      = f"solution/debug_solution_k={params['k']}_p={params['p']}.json"
    
    # 构建模型
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)
    # 优化模型
    model = optimize_model(model)
    # 提取并显示结果
    schedule = extract_results(model, cct=cct, d=d, t_start=t_start, t_end=t_end, 
                             u=u, r=r, t_reconf_start=t_reconf_start, 
                             t_reconf_end=t_reconf_end, t_step_end=t_step_end, 
                             params=params)
    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=True, filename=solution_figure)
    model.write(solution_file) # DEBUG: 
    
    # Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
    plot_schedule(schedule_baseline, params['k'], params['T_reconf'], save_as_pdf=True, filename=baseline_figure)
    model.write(baseline_file) # DEBUG: 

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
    
    # DEBUG: debug_mode
    debug_mode = 2 # {0, 1, 2, ...}
    if debug_mode == 1:
        '''
        双模型交叉验证
        '''
        # 交叉验证 1 - pre: model-debug create and optimize
        model_debug, cct_debug, d_debug, t_start_debug, t_end_debug, u_debug, r_debug, t_reconf_start_debug, t_reconf_end_debug, t_step_end_debug = build_model(params, debug_model=True)

        model_debug = optimize_model(model_debug)
        schedule_debug = extract_results(model_debug, cct=cct_debug, d=d_debug, t_start=t_start_debug, t_end=t_end_debug, 
                                u=u_debug, r=r_debug, t_reconf_start=t_reconf_start_debug, 
                                t_reconf_end=t_reconf_end_debug, t_step_end=t_step_end_debug, 
                                params=params)
        plot_schedule(schedule_debug, params['k'], params['T_reconf'], save_as_pdf=True, filename=debug_solution_figure)
        model_debug.write(debug_solution_file) # DEBUG: 
            
        log.info("Comparison:")
        cct_debug_optimized = cct_debug.X - params['T_reconf']
        cct_baseline = cct_baseline - params['T_reconf']
        log.info(f"Optimized CCT with debug model: {(cct_debug_optimized) * 1000:.2f} ms")
        log.info(f"Baseline CCT: {cct_baseline * 1000:.2f} ms")
        improvement = ((cct_baseline - cct_debug_optimized) / cct_baseline) * 100 if cct_baseline != 0 else 0
        log.info(f"Improvement: {improvement:.2f}%")
        
        # 交叉验证 1
        load_and_validate_solution(params, debug_solution_file, if_debug_model=False)
        
        # 交叉验证 2
        load_and_validate_solution(params, solution_file, if_debug_model=True)

    elif debug_mode == 2:
        '''
        和手动构造的解进行对比分析
        '''
        compare_file = "solution/modified_solution_k=2_p=8.json"
        load_and_validate_solution(params,compare_file, if_debug_model=True)



if __name__ == "__main__":
    log.basicConfig(level=log.INFO, format='%(message)s')
    main()