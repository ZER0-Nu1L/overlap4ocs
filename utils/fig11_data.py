"""Strict Fig. 11 grid and metric preparation shared by CLI and notebook."""
import itertools
import math
from utils.fig11_validation import cct_metrics, tolerance

ALGORITHMS = ('ar_having-doubling', 'a2a_pairwise', 'a2a_bruck')
LATENCIES = (.02, .2, 2., 20.)
SIZES = (.125, .5, 2., 8., 32., 128., 512.)


def validate_grid(rows, sizes=SIZES, latencies=LATENCIES, budget=120):
    expected = set(itertools.product(ALGORITHMS, latencies, sizes))
    seen, result = set(), []
    for row in rows:
        key = (row['algorithm'], float(row['T_reconf']), float(row['message_mib']))
        if key not in expected or key in seen:
            raise ValueError(f'Unexpected/duplicate Fig. 11 point: {key}')
        seen.add(key)
        for name,value in dict(p=256,k=4,B=25,T_lat=.02,solver_time_limit=budget,solver_gap=.05,solver_threads=8,solver_seed=1).items():
            if name not in row or float(row[name]) != value:
                raise ValueError(f'Mixed/missing parameter {name}: {key}')
        if row['status'] != 'success' or row['solver'] != 'pulp':
            raise ValueError(f'Failed run or wrong solver: {key}')
        vals = [float(row[x]) for x in ('baseline_cct','optimized_cct','ideal_cct')]
        if not all(math.isfinite(x) and x > 0 for x in vals):
            raise ValueError(f'Invalid CCT: {key}')
        baseline, swot, ideal = vals
        if swot < ideal-tolerance(swot, ideal) or swot > baseline+tolerance(swot, baseline):
            raise ValueError(f'Inconsistent CCT order for Fig. 11 point: {key}')
        result.append(dict(row, **cct_metrics(*vals)))
    if seen != expected:
        raise ValueError(f'Incomplete Fig. 11 grid: {len(seen)}/{len(expected)}; missing {expected-seen}')
    return result
