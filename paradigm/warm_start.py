import logging as log
from typing import Any, Dict, Tuple

WarmStartDict = Dict[str, Dict[Tuple[int, int], float]]


def build_baseline_warm_start(schedule: list[dict], params: dict, cct_value: float) -> Dict[str, Any] | None:
    """Convert baseline schedule into variable assignments for warm-starting the MILP."""
    if not schedule:
        return None
    num_steps = params.get('num_steps', 0)
    k = params.get('k', 0)
    warm = {
        'd': {},
        't_start': {},
        't_end': {},
        'u': {},
        'r': {},
        't_reconf_start': {},
        't_reconf_end': {},
        't_step_end': {i: 0.0 for i in range(1, num_steps + 1)},
        'cct': cct_value,
    }
    for record in schedule:
        step = int(record.get('step', 0))
        ocs = int(record.get('ocs', 0))
        if not step or not ocs or step > num_steps or ocs > k:
            continue
        key = (step, ocs)
        warm['d'][key] = float(record.get('d', 0.0))
        warm['t_start'][key] = float(record.get('t_start', 0.0))
        warm['t_end'][key] = float(record.get('t_end', 0.0))
        warm['u'][key] = 1.0 if record.get('used') else 0.0
        warm['r'][key] = 1.0 if record.get('reconf') else 0.0
        warm['t_reconf_start'][key] = float(record.get('t_reconf_start', 0.0))
        warm['t_reconf_end'][key] = float(record.get('t_reconf_end', 0.0))
        if record.get('used'):
            warm['t_step_end'][step] = max(warm['t_step_end'][step], float(record.get('t_end', 0.0)))
    return warm


def apply_warm_start(solver_name: str, variables: dict[str, Any], warm: Dict[str, Any] | None) -> bool:
    if not warm:
        return False

    def set_value(var_obj, value):
        if var_obj is None:
            return
        if solver_name == 'gurobi':
            try:
                var_obj.Start = value
            except AttributeError:
                var_obj.setAttr('Start', value)
        else:
            setter = getattr(var_obj, 'setInitialValue', None)
            if callable(setter):
                setter(value)
            else:
                setattr(var_obj, 'start', value)

    try:
        for key, val in warm.get('d', {}).items():
            set_value(variables['d'][key], val)
        for key, val in warm.get('t_start', {}).items():
            set_value(variables['t_start'][key], val)
        for key, val in warm.get('t_end', {}).items():
            set_value(variables['t_end'][key], val)
        for key, val in warm.get('u', {}).items():
            set_value(variables['u'][key], val)
        for key, val in warm.get('r', {}).items():
            set_value(variables['r'][key], val)
        for key, val in warm.get('t_reconf_start', {}).items():
            set_value(variables['t_reconf_start'][key], val)
        for key, val in warm.get('t_reconf_end', {}).items():
            set_value(variables['t_reconf_end'][key], val)
        for step, val in warm.get('t_step_end', {}).items():
            set_value(variables['t_step_end'][step], val)
        set_value(variables['cct'], warm.get('cct', 0))
    except Exception as exc:  # noqa: BLE001
        log.warning(f"Failed to apply warm start: {exc}")
        return False
    return True
