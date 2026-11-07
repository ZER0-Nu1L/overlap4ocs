"""CBC termination evidence; PuLP's LpStatus is not an optimality proof."""
import re

NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def parse_cbc_log(text, incumbent=None, sol_status=None):
    results = re.findall(r'^Result - (.+)$', text, re.M)
    reason = results[-1].strip() if results else 'unknown'
    if reason == 'Optimal solution found':
        termination = 'optimal'
    elif reason == 'Optimal solution found (within gap tolerance)':
        termination = 'gap_tolerance'
    elif 'time limit' in reason.lower():
        termination = 'time_limit'
    elif 'infeasible' in reason.lower():
        termination = 'infeasible'
    elif 'unbounded' in reason.lower():
        termination = 'unbounded'
    else:
        termination = 'unknown'
    # LpSolutionOptimal=1, LpSolutionIntegerFeasible=2. LP relaxation values
    # may still populate varValue after an integer-infeasible termination.
    has_incumbent = sol_status in (1, 2) and incumbent is not None
    if 'No feasible solution found' in text or termination in ('infeasible', 'unbounded'):
        has_incumbent = False
    reported_bounds = re.findall(r'best possible (' + NUMBER + r')', text)
    if not reported_bounds:
        reported_bounds = re.findall(r'^Lower bound:\s*(' + NUMBER + r')', text, re.M)
    token = reported_bounds[-1] if reported_bounds else None
    bound = float(token) if token else None
    # CBC summaries round bounds. Store both the printed number and a lower
    # endpoint of its rounding interval; never claim extra decimal precision.
    conservative = None
    if token:
        coefficient, _, exp = token.lower().partition('e')
        decimals = len(coefficient.partition('.')[2])
        conservative = bound - .5 * 10 ** ((int(exp) if exp else 0) - decimals)
    proven = termination == 'optimal' and has_incumbent
    if proven:
        bound = conservative = incumbent
    gaps = re.findall(r'^Gap:\s*(' + NUMBER + r')', text, re.M)
    versions = re.findall(r'^Version:\s*(.+)$', text, re.M)
    return {'termination': termination, 'termination_text': reason,
            'has_incumbent': has_incumbent, 'proven_optimal': proven,
            'incumbent_raw_ms': incumbent if has_incumbent else None,
            'bound_reported_raw_ms': bound, 'bound_conservative_raw_ms': conservative,
            'reported_cbc_gap': float(gaps[-1]) if gaps else None,
            'pulp_sol_status': sol_status, 'cbc_version': versions[-1].strip() if versions else None}
