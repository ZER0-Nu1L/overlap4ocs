"""Collective communication algorithm parameter utilities."""
from __future__ import annotations

from typing import Dict


def compute_algorithm_params(algorithm: str, p: int, m: float) -> Dict[str, object]:
    """Return derived parameters for the chosen collective algorithm."""
    if algorithm == 'rs_having-doubling':
        return compute_rs_having_doubling_params(p, m)
    if algorithm == 'ag_having-doubling':
        return compute_ag_having_doubling_params(p, m)
    if algorithm == 'ar_ring':
        return compute_ar_ring_params(p, m)
    if algorithm == 'ar_having-doubling':
        return compute_ar_having_doubling_params(p, m)
    if algorithm == 'ar_recursive-doubling':
        return compute_ar_recursive_doubling_params(p, m)
    if algorithm == 'a2a_bruck':
        return compute_a2a_bruck_params(p, m)
    if algorithm == 'a2a_pairwise':
        return compute_a2a_pairwise_params(p, m)
    raise ValueError(f"Unsupported algorithm: {algorithm}")

# --- Below are implementations of parameter computations for different algorithms ---

# Rabenseifner's halving-doubling algorithm for ReduceScatter
def compute_rs_having_doubling_params(p: int, m: float) -> Dict[str, object]:
    """Rabenseifner's algorithm for ReduceScatter (halving-doubling)."""
    p_new = 2 ** (p.bit_length() - 1)
    num_steps = (p_new - 1).bit_length()
    return {
        'p': p_new,
        'num_steps': num_steps,
        'm_i': compute_rs_hd_message_sizes(m, num_steps),
        'configurations': compute_rs_hd_configurations(num_steps),
    }

def compute_rs_hd_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    m_i: Dict[int, float] = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m / (2 ** i)
    return m_i

def compute_rs_hd_configurations(num_steps: int) -> Dict[int, int]:
    configurations: Dict[int, int] = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations

# Rabenseifner's halving-doubling algorithm for AllGather
def compute_ag_having_doubling_params(p: int, m: float) -> Dict[str, object]:
    """Rabenseifner's algorithm for AllGathers (halving-doubling)."""
    p_new = 2 ** (p.bit_length() - 1)
    num_steps = (p_new - 1).bit_length()
    return {
        'p': p_new,
        'num_steps': num_steps,
        'm_i': compute_ag_hd_message_sizes(m, num_steps),
        'configurations': compute_ag_hd_configurations(num_steps),
    }

def compute_ag_hd_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    m_i: Dict[int, float] = {}
    for i in range(num_steps, 0, -1):
        m_i[i] = m / (2 ** i)
    return m_i

def compute_ag_hd_configurations(num_steps: int) -> Dict[int, int]:
    configurations: Dict[int, int] = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations


# Rabenseifner's halving-doubling algorithm for AllReduce
def compute_ar_having_doubling_params(p: int, m: float) -> Dict[str, object]:
    """Rabenseifner's algorithm for AllReduce (halving-doubling)."""
    p_new = 2 ** (p.bit_length() - 1)
    s = (p_new - 1).bit_length()
    num_steps = 2 * s
    return {
        'p': p_new,
        'num_steps': num_steps,
        'm_i': compute_ar_hd_message_sizes(m, s, num_steps),
        'configurations': compute_ar_hd_configurations(s, num_steps),
    }

def compute_ar_hd_message_sizes(m: float, s: int, num_steps: int) -> Dict[int, float]:
    m_i: Dict[int, float] = {}
    for i in range(1, num_steps + 1):
        if i <= s:
            m_i[i] = m / (2 ** i)
        else:
            m_i[i] = m_i[2 * s + 1 - i]
    return m_i

def compute_ar_hd_configurations(s: int, num_steps: int) -> Dict[int, int]:
    configurations: Dict[int, int] = {}
    for i in range(1, num_steps + 1):
        configurations[i] = min(i, 2 * s - i + 1)
    return configurations

# recursive-doubling algorithm for AllReduce
def compute_ar_recursive_doubling_params(p: int, m: float) -> Dict[str, object]:
    """Rabenseifner's algorithm for AllReduce (recursive-doubling)."""
    p_new = 2 ** (p.bit_length() - 1)
    num_steps = (p_new - 1).bit_length()
    return {
        'p': p_new,
        'num_steps': num_steps,
        'm_i': compute_ar_rd_message_sizes(m, num_steps),
        'configurations': compute_ar_rd_configurations(num_steps),
    }

def compute_ar_rd_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    m_i: Dict[int, float] = {}
    for i in range(1, num_steps + 1):
        m_i[i] = m
    return m_i

def compute_ar_rd_configurations(num_steps: int) -> Dict[int, int]:
    configurations: Dict[int, int] = {}
    for i in range(1, num_steps + 1):
        configurations[i] = i
    return configurations



# All-to-all pairwise algorithm
def compute_a2a_pairwise_params(p: int, m: float) -> Dict[str, object]:
    num_steps = p - 1
    return {
        'p': p,
        'num_steps': num_steps,
        'm_i': compute_a2a_pairwise_message_sizes(m, num_steps),
        'configurations': compute_a2a_pairwise_configurations(num_steps),
    }

def compute_a2a_pairwise_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    return {i: m / num_steps for i in range(1, num_steps + 1)}

def compute_a2a_pairwise_configurations(num_steps: int) -> Dict[int, int]:
    return {i: i for i in range(1, num_steps + 1)}


# All-to-all Bruck algorithm
def compute_a2a_bruck_params(p: int, m: float) -> Dict[str, object]:
    p_new = 2 ** (p.bit_length() - 1)
    num_steps = (p_new - 1).bit_length()
    return {
        'p': p_new,
        'num_steps': num_steps,
        'm_i': compute_a2a_bruck_message_sizes(m, num_steps),
        'configurations': compute_a2a_bruck_configurations(num_steps),
    }

def compute_a2a_bruck_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    return {i: m for i in range(1, num_steps + 1)}

def compute_a2a_bruck_configurations(num_steps: int) -> Dict[int, int]:
    return {i: i for i in range(1, num_steps + 1)}

# Ring algorithm
def compute_ar_ring_params(p: int, m: float) -> Dict[str, object]:
    num_steps = p - 1
    return {
        'p': p,
        'num_steps': num_steps,
        'm_i': compute_ar_ring_message_sizes(m, num_steps),
        'configurations': compute_ar_ring_configurations(num_steps),
    }

def compute_ar_ring_message_sizes(m: float, num_steps: int) -> Dict[int, float]:
    return {i: m / num_steps for i in range(1, num_steps + 1)}

def compute_ar_ring_configurations(num_steps: int) -> Dict[int, int]:
    return {i: i/i for i in range(1, num_steps + 1)}

# TODO: Recursive doubling algorithm

# TODO: Add more algorithms as needed