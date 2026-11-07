#!/usr/bin/env python3
"""Run one Fig. 11 instance with complete, isolated scientific evidence.

Compatible with matrix_runner's --config/--metrics-file/--run-id arguments.
Every trial runs in its own process, so resource peak counters do not mix runs.
"""
import argparse
import hashlib
import json
import logging
import math
import platform
import resource
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instance_parser import get_parameters
from paradigm.baseline import compute_baseline_schedule
from paradigm.ideal import compute_ideal_time
from paradigm.model_pulp import build_model
from paradigm.solver_wrapper import solve_model
from utils.fig11_validation import cct_metrics, model_residuals, replay, tolerance, validate_schedule
from utils.scheduler_analysis import extract_results


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--metrics-file', required=True)
    parser.add_argument('--run-id')
    parser.add_argument('--program-config')
    args = parser.parse_args()
    started = time.monotonic()
    output = Path(args.metrics_file).resolve().parent
    output.mkdir(parents=True, exist_ok=True)
    params = get_parameters(args.config)
    if params['solver'] != 'pulp':
        raise ValueError('Fig. 11 correction uses the CBC backend')
    baseline_raw, baseline_schedule = compute_baseline_schedule(params)
    baseline_validation = validate_schedule(params, baseline_schedule, baseline_raw)
    if not baseline_validation['valid']:
        raise ValueError(baseline_validation)
    ideal = compute_ideal_time(params)
    independent_ideal = sum(params['m_i'].values()) / (params['B'] * params['k']) + params['num_steps'] * params['T_lat']
    changes = 1 + sum(params['configurations'][i] != params['configurations'][i-1] for i in range(2, params['num_steps'] + 1))
    independent_baseline = independent_ideal + changes * params['T_reconf']
    if not math.isclose(ideal, independent_ideal, abs_tol=1e-9) or not math.isclose(baseline_raw, independent_baseline, abs_tol=1e-9):
        raise ValueError('Independent baseline/Ideal formula mismatch')
    write_json(output / 'baseline-schedule.json', baseline_schedule)
    built = time.monotonic()
    variables = build_model(params)
    model, cct, d, ts, te, u, r, rs, re, ends = variables
    model.writeLP(str(output / 'model.lp'))
    build_seconds = time.monotonic() - built
    solving = time.monotonic()
    solve_model(model, 'pulp', solver_gap=params['solver_gap'], solver_time_limit=params['solver_time_limit'],
                solver_threads=params.get('solver_threads'), solver_seed=params.get('solver_seed'),
                solver_artifact_dir=str(output / 'solver'))
    solve_seconds = time.monotonic() - solving
    evidence = model.solver_evidence
    write_json(output / 'solver-variables.json', {v.name: v.varValue for v in model.variables()})
    incumbent_schedule, incumbent_raw = None, None
    validation = {'valid': False, 'errors': ['no integer incumbent']}
    residuals = model_residuals(model)
    if evidence['has_incumbent']:
        incumbent_raw = cct.varValue
        incumbent_schedule = extract_results(model, cct=cct, d=d, t_start=ts, t_end=te, u=u, r=r,
                    t_reconf_start=rs, t_reconf_end=re, t_step_end=ends, params=params)
        validation = validate_schedule(params, incumbent_schedule, incumbent_raw, {i: v.varValue for i, v in ends.items()})
        write_json(output / 'incumbent-schedule.json', incumbent_schedule)
    write_json(output / 'validation.json', {'baseline': baseline_validation, 'incumbent': validation, 'model': residuals})
    if evidence['has_incumbent'] and (not validation['valid'] or not residuals['valid']):
        raise ValueError('Integer incumbent failed validation; see validation.json')
    fallback = incumbent_raw is None or incumbent_raw > baseline_raw + tolerance(incumbent_raw or 0, baseline_raw)
    schedule = baseline_schedule if fallback else incumbent_schedule
    selected_raw = baseline_raw if fallback else incumbent_raw
    selected_validation = validate_schedule(params, schedule, selected_raw)
    allowed_raw, allowed_schedule = replay(params, schedule)
    blocked_raw, blocked_schedule = replay(params, schedule, no_overlap=True)
    if allowed_raw > selected_raw + tolerance(allowed_raw, selected_raw):
        raise ValueError('Earliest replay exceeds original schedule')
    if blocked_raw + tolerance(blocked_raw, allowed_raw) < allowed_raw:
        raise ValueError('No-overlap replay unexpectedly faster')
    write_json(output / 'selected-schedule.json', schedule)
    write_json(output / 'replay-overlap.json', allowed_schedule)
    write_json(output / 'replay-no-overlap.json', blocked_schedule)
    offset = params['T_reconf']
    selected, baseline = selected_raw - offset, baseline_raw - offset
    bound = evidence['bound_conservative_raw_ms']
    adjusted_bound = bound - offset if bound is not None else None
    gap = (selected - adjusted_bound) / selected if adjusted_bound is not None and selected > 0 else None
    if gap is not None and gap < -1e-5:
        raise ValueError('Solver bound exceeds selected feasible objective')
    patch = subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)
    (output / 'code.diff').write_bytes(patch)
    # Untracked new modules must also be recorded; matrix series additionally
    # freezes a full tracked+untracked Python source snapshot before starting.
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for folder in ('utils','paradigm','config','scripts') for p in (ROOT/folder).glob('*.py')}
    python_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    metrics = {
        'schema_version': 1, 'run_id': args.run_id, 'status': 'success', 'params': params,
        'cct': dict(optimized=selected, baseline=baseline, ideal=ideal, oneshot=None),
        'raw_cct': dict(optimized=selected_raw, baseline=baseline_raw, incumbent=incumbent_raw),
        'time_origin': {'initial_preconfiguration_excluded_ms': offset},
        'metrics': cct_metrics(baseline, selected, ideal),
        'improvement_percent': {'over_baseline': 100 * (baseline - selected) / baseline},
        'solver': dict(evidence, threads=params.get('solver_threads'), seed=params.get('solver_seed'),
                       target_gap=params['solver_gap'], time_limit_s=params['solver_time_limit'],
                       adjusted_bound_ms=adjusted_bound, selected_cct_gap_upper=gap),
        'selection': {'fallback_used': fallback, 'source': 'baseline' if fallback else 'solver_incumbent',
                      'reason': ('no_integer_incumbent' if incumbent_raw is None else 'baseline_faster') if fallback else None},
        'validation': selected_validation,
        'mechanism': {'overlap_cct_ms': allowed_raw-offset, 'no_overlap_cct_ms': blocked_raw-offset,
                      'saved_ms': blocked_raw-allowed_raw,
                      'saved_pct': 100*(blocked_raw-allowed_raw)/(blocked_raw-offset),
                      'original_extra_wait_ms': selected_raw-allowed_raw,
                      'definition': 'Fixed d/u/r; earliest timing; global reconfiguration/transmission barriers in no-overlap'},
        'timing': {'model_build_seconds': build_seconds, 'solve_wall_seconds': solve_seconds,
                   'total_seconds': time.monotonic()-started},
        'resources': {'python_peak_rss_kib': python_rss, 'max_child_peak_rss_kib': child_rss,
                      'conservative_peak_sum_kib': python_rss+child_rss},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'packages': {x: version(x) for x in ('pulp','numpy','pandas','matplotlib','networkx','toml','pyvis')},
                        'git_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        'code_diff_sha256': hashlib.sha256(patch).hexdigest(), 'source_sha256': sources},
        'units': {'message': 'decimal MB', 'B': 'decimal GB/s = MB/ms', 'time': 'ms',
                  'message_mib_column': 'legacy name; numeric values passed unchanged to m (decimal MB)'},
    }
    write_json(Path(args.metrics_file), metrics)
    print(json.dumps({'cct': metrics['cct'], 'solver': metrics['solver'], 'selection': metrics['selection']}, indent=2))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    main()
