"""Independent schedule validation and fixed-decision earliest-time replay.

Raw time is ms, payload is decimal MB, B is MB/ms (= decimal GB/s).
Tolerance accounts for CBC's text solution precision and is always reported.
"""
import math

ABS_TOL = 1e-6
REL_TOL = 2e-7


def tolerance(a, b):
    return ABS_TOL + REL_TOL * max(abs(a), abs(b))


def validate_schedule(params, schedule, cct, step_ends=None, no_overlap=False):
    errors = []

    def check(ok, why):
        if not ok:
            errors.append(why)

    def ge(a, b, why):
        check(a + tolerance(a, b) >= b, why)

    def eq(a, b, why):
        check(abs(a - b) <= tolerance(a, b), why)

    n, k = params['num_steps'], params['k']
    expected = {(i, j) for i in range(1, n + 1) for j in range(1, k + 1)}
    records = {}
    fields = ('d', 'used', 'reconf', 't_start', 't_end', 't_reconf_start', 't_reconf_end')
    for item in schedule or []:
        key = (item.get('step'), item.get('ocs'))
        check(key in expected and key not in records, f'grid/duplicate {key}')
        for f in fields:
            v = item.get(f)
            check(isinstance(v, (int, float)) and math.isfinite(v), f'nonfinite/missing {key} {f}')
        records[key] = item
    check(set(records) == expected, 'incomplete schedule grid')
    check(isinstance(cct, (int, float)) and math.isfinite(cct), 'nonfinite CCT')
    if errors:
        return dict(valid=False, errors=errors, abs_tol=ABS_TOL, rel_tol=REL_TOL)
    config = {j: None for j in range(1, k + 1)}
    available = {j: 0.0 for j in config}
    previous = 0.0
    for i in range(1, n + 1):
        items = [records[i, j] for j in config]
        eq(sum(x['d'] for x in items), params['m_i'][i], f'data conservation {i}')
        active = [x for x in items if x['used'] > .5]
        end = max((x['t_end'] for x in active), default=0.0)
        declared = step_ends[i] if step_ends is not None else end
        ge(declared, end, f'step completion {i}')
        barrier = max([previous] + [x['t_reconf_end'] for x in items if x['reconf'] > .5])
        for x in items:
            j = x['ocs']
            key = (i, j)
            u, r = x['used'], x['reconf']
            for f in fields:
                ge(x[f], 0.0, f'negative {key} {f}')
            for f, v in (('used', u), ('reconf', r)):
                check(abs(v - round(v)) <= ABS_TOL and round(v) in (0, 1), f'nonbinary {key} {f}')
            ge(u, r, f'reconfiguration without use {key}')
            if u < .5:
                eq(x['d'], 0.0, f'data on unused plane {key}')
            # Scale duration comparisons by absolute time to reflect text rounding.
            duration = x['d'] / params['B'] + params.get('T_lat', 0) * u
            eq(x['t_end'], x['t_start'] + duration, f'transmission duration {key}')
            eq(x['t_reconf_end'], x['t_reconf_start'] + params['T_reconf'] * r, f'reconfiguration duration {key}')
            ge(x['t_start'], x['t_reconf_end'], f'transmission before ready {key}')
            ge(x['t_start'], previous, f'cross-step dependency {key}')
            ge(x['t_reconf_start'], available[j], f'plane conflict {key}')
            if r > .5:
                config[j] = params['configurations'][i]
            if u > .5:
                check(config[j] == params['configurations'][i], f'wrong physical configuration {key}')
            if no_overlap:
                ge(x['t_reconf_start'], previous, f'early reconfiguration {key}')
                if u > .5:
                    ge(x['t_start'], barrier, f'no-overlap phase barrier {key}')
            if u > .5:
                available[j] = max(available[j], x['t_end'])
            if r > .5:
                available[j] = max(available[j], x['t_reconf_end'])
        ge(cct, declared, f'CCT lower bound {i}')
        previous = declared
    return dict(valid=not errors, errors=errors, abs_tol=ABS_TOL, rel_tol=REL_TOL)


def replay(params, schedule, no_overlap=False):
    """Longest-path timing with fixed d/u/r, step order, and plane order.

    No-overlap adds barriers before each reconstruction and transmission phase.
    Reconfigurations on different planes can run in parallel. Inactive records
    preserve the original model's zero-duration dependency constraints.
    """
    records = {(x['step'], x['ocs']): x for x in schedule}
    available = {j: 0.0 for j in range(1, params['k'] + 1)}
    previous, result, ends = 0.0, [], {}
    for i in range(1, params['num_steps'] + 1):
        items = []
        for j in available:
            x = records[i, j]
            u, r = round(x['used']), round(x['reconf'])
            rs = max(available[j], previous if no_overlap else 0.0)
            re = rs + r * params['T_reconf']
            items.append(dict(x, used=u, reconf=r, t_reconf_start=rs, t_reconf_end=re))
        barrier = max([previous] + [x['t_reconf_end'] for x in items if x['reconf']])
        for x in items:
            start = max(previous, x['t_reconf_end'], barrier if no_overlap else 0.0)
            x['t_start'] = start
            x['t_end'] = start + x['d'] / params['B'] + params.get('T_lat', 0) * x['used']
            if x['used']:
                available[x['ocs']] = x['t_end']
            if x['reconf']:
                available[x['ocs']] = max(available[x['ocs']], x['t_reconf_end'])
        previous = max(x['t_end'] for x in items if x['used'])
        ends[i] = previous
        result.extend(items)
    cct = max(ends.values())
    report = validate_schedule(params, result, cct, ends, no_overlap=no_overlap)
    if not report['valid']:
        raise ValueError(report)
    return cct, result


def model_residuals(model):
    """Check every PuLP variable/linear constraint, including auxiliaries."""
    errors = []
    for v in model.variables():
        x = v.varValue
        if x is None or not math.isfinite(x):
            errors.append(f'missing/nonfinite variable {v.name}')
            continue
        if v.lowBound is not None and x < v.lowBound - tolerance(x, v.lowBound):
            errors.append(f'lower bound {v.name}')
        if v.upBound is not None and x > v.upBound + tolerance(x, v.upBound):
            errors.append(f'upper bound {v.name}')
        if v.cat == 'Integer' and abs(x - round(x)) > ABS_TOL:
            errors.append(f'integrality {v.name}')
    if not errors:
        for name, c in model.constraints.items():
            residual = c.value()
            scale = sum(abs(v.varValue * a) for v, a in c.items()) + abs(c.constant)
            tol = ABS_TOL + REL_TOL * scale
            bad = abs(residual) > tol if c.sense == 0 else residual * c.sense < -tol
            if bad:
                errors.append(f'{name}: residual={residual:g}, tolerance={tol:g}')
    return dict(valid=not errors, errors=errors, abs_tol=ABS_TOL, rel_tol=REL_TOL)


def cct_metrics(baseline, swot, ideal):
    if not all(math.isfinite(x) and x > 0 for x in (baseline, swot, ideal)):
        raise ValueError('CCTs must be finite and positive')
    return {'baseline_gap_pct': 100 * (baseline - ideal) / baseline,
            'swot_gap_pct': 100 * (swot - ideal) / swot,
            'gain_pct': 100 * (baseline - swot) / baseline}
