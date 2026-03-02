# instance_parser.py
import logging as log
import toml
import os

from config.cc_algorithm import compute_algorithm_params

def get_parameters(config_file = 'config/instance.toml'):
    # Default parameters
    params = {
        'solver': 'pulp',                 # Optimization solver: 'gurobi', 'pulp', 'pulp_gurobi', or 'copt'
        'k': 2,                             # Number of OCS
        'B': 400 * 1024 * 1024 / 8,     # Bandwidth per OCS (bytes/ms)
        'T_reconf': 0.2,                      # Reconfiguration time (ms)
        'T_lat': 0.02,                      # End-to-end base latency (ms)
        'p': 16,                            # Number of compute nodes
        'm': 32 * 1024 * 1024,              # Total message size (bytes)
        'algorithm': 'ar_having-doubling',  # CC Algorithm: 'ar_having-doubling', 'a2a_pairwise', 'a2a_bruck', ... check in cc_algorithm.py
        'solver_gap': None,                 # Relative MIP gap tolerance (None -> solver default)
        'solver_time_limit': None,          # Time limit in seconds (None -> solver default)
    }
    params['B'] = params['B'] / params['k']

    # Load parameters from TOML file if it exists
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = toml.load(f)
            # Update default parameters with values from config file
            for key, value in config.items():
                params[key] = value
            log.info(f"Parameters loaded from {config_file}")
        except Exception as e:
            log.warning(f"Failed to load parameters from {config_file}: {e}")
    
    # Validate parameters
    validate_parameters(params)

    # Algorithm-specific parameter calculation
    params.update(compute_algorithm_params(params['algorithm'], params['p'], params['m']))

    log.info(params)
    return params

def validate_parameters(params):
    # Validate solver
    solver = params.get('solver')
    if solver == 'gurobi':
        try:
            import gurobipy  # noqa: F401
            log.info("Gurobi solver is available")
        except ImportError:
            raise ValueError("Gurobi solver specified but gurobipy cannot be imported")
    elif solver == 'pulp':
        try:
            import pulp  # noqa: F401
            log.info("PuLP solver is available")
        except ImportError:
            raise ValueError("PuLP solver specified but pulp cannot be imported")
    elif solver == 'pulp_gurobi':
        try:
            # Ensure PuLP exposes the GUROBI_CMD interface before runtime
            import pulp
            if not hasattr(pulp, 'GUROBI_CMD'):
                raise ImportError("PuLP installation lacks GUROBI_CMD interface")
            log.info("PuLP (Gurobi backend) solver is available")
        except ImportError as exc:
            raise ValueError("pulp_gurobi solver specified but PuLP Gurobi bindings are unavailable") from exc
    elif solver == 'copt':
        try:
            from pulp import COPT  # noqa: F401
            log.info("COPT solver is available")
        except ImportError:
            raise ValueError("COPT solver specified but COPT cannot be imported from pulp")
    else:
        raise ValueError(f"Unsupported solver: {solver}")
    
    # Validate numeric parameters
    for param_name in ['k', 'B', 'T_reconf', 'T_lat', 'p', 'm']:
        value = params.get(param_name)
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"Parameter {param_name} must be a positive number")
    
    solver_gap = params.get('solver_gap')
    if solver_gap is not None and solver_gap < 0:
        raise ValueError("solver_gap must be non-negative when provided")

    solver_time_limit = params.get('solver_time_limit')
    if solver_time_limit is not None and solver_time_limit < 0:
        raise ValueError("solver_time_limit must be non-negative when provided")
