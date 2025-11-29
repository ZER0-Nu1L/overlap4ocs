# instance_parser.py
import logging as log
import toml
import os

import gurobipy
import pulp
from pulp import COPT

def get_parameters(config_file = 'config/instance.toml'):
    # Default parameters
    params = {
        'solver': 'gurobi',                 # Optimization solver: 'gurobi', 'pulp', or 'copt'
        'k': 2,                             # Number of OCS
        'B': 400 * 1024 * 1024 / 8,     # Bandwidth per OCS (bytes/ms)
        'T_reconf': 0.2,                      # Reconfiguration time (ms)
        'T_lat': 0.02,                      # End-to-end base latency (ms)
        'p': 16,                            # Number of compute nodes
        'm': 32 * 1024 * 1024,              # Total message size (bytes)
        'algorithm': 'ar_having-doubling'   # CC Algorithm: 'ar_having-doubling', 'a2a_pairwise', 'a2a_bruck'
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
    algorithm = params['algorithm']
    if algorithm == 'a2a_bruck':
        params.update(compute_a2a_bruck_params(params['p'], params['m']))
    elif algorithm == 'a2a_pairwise':
        params.update(compute_a2a_pairwise_params(params['p'], params['m']))
    elif algorithm == 'ar_having-doubling':
        params.update(compute_having_doubling_params(params['p'], params['m']))
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    log.info(params)
    return params

def validate_parameters(params):
    # Validate solver
    solver = params.get('solver')
    if solver == 'gurobi':
        try:
            log.info("Gurobi solver is available")
        except ImportError:
            raise ValueError("Gurobi solver specified but gurobipy cannot be imported")
    elif solver == 'pulp':
        try:
            log.info("PuLP solver is available")
        except ImportError:
            raise ValueError("PuLP solver specified but pulp cannot be imported")
    elif solver == 'copt':
        try:
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
    
    # Validate algorithm
    algorithm = params.get('algorithm')
    valid_algorithms = ['ar_having-doubling', 'a2a_pairwise', 'a2a_bruck']
    if algorithm not in valid_algorithms:
        raise ValueError(f"Algorithm must be one of {valid_algorithms}")

## Having Doubling（Rabenseifner's Algorithm）
def compute_having_doubling_params(p, m):
    p_new = 2 ** ((p).bit_length() - 1)  # NOTE: p_new is a power of 2 less than or equal to p
    s = (p_new - 1).bit_length()         # NOTE: (p - 1).bit_length() <=> ceil(log2(p))
    
    num_steps = 2 * s
    return {
        'p': p_new, # FIXME: For now.
        's': s,
        'num_steps': num_steps,
        'm_i': compute_hd_message_sizes(m, s, num_steps),
        'configurations': compute_hd_configurations(s, num_steps)
    }

def compute_hd_message_sizes(m, s, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        if i <= s:
            m_i[i] = m / (2 ** i)
        else:
            m_i[i] = m_i[2 * s + 1 - i]
    return m_i

def compute_hd_configurations(s, num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = min(i, 2 * s - i + 1)
    return configurations

## All-to-all（Pairwise Exchange）
def compute_a2a_pairwise_params(p, m):
    num_steps = p - 1
    return {
        'p': p, # FIXME: For now.
        'num_steps': num_steps,
        'm_i': compute_a2a_pairwise_message_sizes(m, num_steps),
        'configurations': compute_a2a_pairwise_configurations(num_steps)
    }

def compute_a2a_pairwise_message_sizes(m, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m / num_steps
    return m_i    

def compute_a2a_pairwise_configurations(num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations

## All-to-all（Bruck）
def compute_a2a_bruck_params(p, m):
    p_new = 2 ** ((p).bit_length() - 1)  # NOTE: p_new is a power of 2 less than or equal to p
    s = (p_new - 1).bit_length()         # NOTE: (p - 1).bit_length() 即 ceil(log2(p))
    
    num_steps = s
    return {
        'p': p_new, # FIXME: For now.
        's': s,
        'num_steps': num_steps,
        'm_i': compute_a2a_bruck_message_sizes(m, num_steps),
        'configurations': compute_a2a_bruck_configurations(num_steps)
    }

def compute_a2a_bruck_message_sizes(m, num_steps):
    m_i = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m
    return m_i    

def compute_a2a_bruck_configurations(num_steps):
    configurations = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations