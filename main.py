from config import get_parameters
from model import build_model, optimize_model, load_and_validate_solution
from baseline import compute_baseline_schedule
from one_shot import compute_oneshot_schedule
from scheduler_analysis import extract_results, plot_schedule
import logging as log

def main():    
    # 获取参数
    params = get_parameters()
    # .sol or .json
    solution_figure   =  f"figures/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    solution_file    =  f"solution/solution_{params['algorithm']}_break_k={params['k']}_p={params['p']}_m={params['m']}.json"
    baseline_figure   =  f"figures/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    baseline_file    =  f"solution/baseline_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json"
    oneshot_figure    =  f"figures/oneshot_{params['algorithm']}_t_k={params['k']}_p={params['p']}_m={params['m']}.pdf"
    oneshot_file     =  f"solution/oneshot_{params['algorithm']}__k={params['k']}_p={params['p']}_m={params['m']}.json"

    
    # 构建模型
    model, cct, d, t_start, t_end, u, r, t_reconf_start, t_reconf_end, t_step_end = build_model(params)
    # 优化模型
    model = optimize_model(model)
    # 提取并显示结果
    schedule = extract_results(model, cct=cct, d=d, t_start=t_start, t_end=t_end, 
                             u=u, r=r, t_reconf_start=t_reconf_start, 
                             t_reconf_end=t_reconf_end, t_step_end=t_step_end, 
                             params=params)
    plot_schedule(schedule, params['k'], params['T_reconf'], save_as_pdf=True, filename=solution_figure, show=False)
    model.write(solution_file) # DEBUG: 
    
    # Baseline
    cct_baseline, schedule_baseline = compute_baseline_schedule(params)
    plot_schedule(schedule_baseline, params['k'], params['T_reconf'], save_as_pdf=True, filename=baseline_figure, show=False)
    model.write(baseline_file) # DEBUG: 

    # One-shot
    cct_oneshot, schedule_oneshot = compute_oneshot_schedule(params)
    if cct_oneshot is not None:
        plot_schedule(schedule_oneshot, params['k'], params['T_reconf'], save_as_pdf=True, filename=oneshot_figure, show=False)
        model.write(oneshot_file) # DEBUG: 
    
    # 显示基线结果
    log.info(f"\nBaseline CCT: {cct_baseline * 1000:.0f} μs")
    for s in schedule_baseline:
        log.info(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d'] / (1024 * 1024):.0f} MB, "
              f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
              f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")

    # 显示one-shot结果
    if cct_oneshot is not None:
        log.info(f"\nOne-shot CCT: {cct_oneshot * 1000:.0f} μs")
        for s in schedule_oneshot:
            log.info(f"Step {s['step']}, OCS {s['ocs']}, Used: {s['used']}, Data: {s['d'] / (1024 * 1024):.0f} MB, "
                  f"TransTime: {s['t_start']:.6f}-{s['t_end']:.6f}, "
                  f"Reconf: {s['reconf']}, ReconfTime: {s['t_reconf_start']:.6f}-{s['t_reconf_end']:.6f}")
    else:
        log.info("\nOne-shot schedule is not feasible for current parameters")

    # 比较三种方案的结果
    log.info("\nComparison:")
    cct_optimized = cct.X - params['T_reconf']
    cct_baseline = cct_baseline - params['T_reconf']
    log.info(f"Optimized CCT: {(cct_optimized) * 1000:.0f} μs")
    log.info(f"Baseline CCT: {cct_baseline * 1000:.0f} μs")
    if cct_oneshot is not None:
        cct_oneshot = cct_oneshot - params['T_reconf']
        log.info(f"One-shot CCT: {cct_oneshot * 1000:.0f} μs")
    
    # DEBUG: 
    import pyperclip
    if cct_oneshot is not None:
        data_str = f"{cct_baseline:.2f}\n{cct_oneshot:.2f}\n{(cct_optimized):.2f}"
        pyperclip.copy(data_str)
        log.info(f"{cct_baseline:.2f}\n{cct_oneshot:.2f}\n{(cct_optimized):.2f}")
    else:
        data_str = f"{cct_baseline:.2f}\nNone\n{(cct_optimized):.2f}"
        pyperclip.copy(data_str)
        log.info(f"{cct_baseline:.2f}\n{cct_oneshot:.2f}\n{(cct_optimized):.2f}")
        

    # 计算改进百分比
    improvement_over_baseline = ((cct_baseline - cct_optimized) / cct_baseline) * 100 if cct_baseline != 0 else 0
    log.info(f"Improvement over baseline: {improvement_over_baseline:.0f}%")
    
    if cct_oneshot is not None:
        improvement_over_oneshot = ((cct_oneshot - cct_optimized) / cct_oneshot) * 100 if cct_oneshot != 0 else 0
        log.info(f"Improvement over one-shot: {improvement_over_oneshot:.0f}%")
    

    # DEBUG: debug_mode
    debug_mode = 0 # {0, 1, 2, ...}
    debug_solution_figure    =  f"figures/debug_solution_k={params['k']}_p={params['p']}.pdf"
    debug_solution_file      =  f"solution/debug_solution_k={params['k']}_p={params['p']}.json"
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
        # cct_baseline = cct_baseline - params['T_reconf'] # NOTE: 重复了
        log.info(f"Optimized CCT with debug model: {(cct_debug_optimized) * 1000:.0f} μs")
        log.info(f"Baseline CCT: {cct_baseline * 1000:.0f} μs")
        improvement = ((cct_baseline - cct_debug_optimized) / cct_baseline) * 100 if cct_baseline != 0 else 0
        log.info(f"Improvement: {improvement:.0f}%")
        
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