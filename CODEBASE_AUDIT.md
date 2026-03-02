# Codebase Audit Report — overlap4ocs (SWOT Scheduler)

> Generated: 2025-01
> Scope: All source code except `logs/` and `archives/`
> Purpose: Provide full context for upcoming refactoring

---

## 1. Project Overview

**SWOT Scheduler (overlap4ocs)** — Joint optimization of OCS (Optical Circuit Switch) reconfiguration and collective communication scheduling via MILP (Mixed Integer Linear Programming) to minimize CCT (Communication Completion Time).

Supported CC algorithms:

- AllReduce: ring / halving-doubling / recursive-doubling
- All-to-All: pairwise / bruck
- ReduceScatter / AllGather: halving-doubling

---

## 2. Module Dependency Graph

```text
main.py  (entry point)
├── config/instance_parser.py    → read TOML, validate params
│   └── config/cc_algorithm.py   → algorithm-specific params (num_steps, m_i, configurations)
├── paradigm/baseline.py         → baseline schedule (no optimization)
├── paradigm/one_shot.py         → one-shot OCS pre-configuration
├── paradigm/ideal.py            → theoretical lower bound
├── paradigm/warm_start.py       → convert baseline/oneshot to warm start
├── paradigm/model_gurobi.py     → Gurobi MILP model
├── paradigm/model_pulp.py       → PuLP MILP model
├── paradigm/solver_wrapper.py   → unified solver interface + validation
└── utils/scheduler_analysis.py  → result extraction + Gantt chart plotting
    └── utils/check_platform.py  → ARM Mac detection

scripts/
├── generate_matrix_configs.py   → expand matrix spec → instance TOMLs
├── matrix_runner.py             → batch experiments → append CSV
└── matrix_archive.py            → archive/cleanup experiment artifacts
```

---

## 3. Module Details

### 3.1 `config/cc_algorithm.py` — CC Algorithm Parameters

| Algorithm | Function | num_steps | Config Pattern |
|-----------|----------|-----------|----------------|
| `rs_having-doubling` | `compute_rs_having_doubling_params` | log₂(p) | each step different |
| `ag_having-doubling` | `compute_ag_having_doubling_params` | log₂(p) | each step different |
| `ar_having-doubling` | `compute_ar_having_doubling_params` | 2×log₂(p) | symmetric front-back |
| `ar_recursive-doubling` | `compute_ar_recursive_doubling_params` | log₂(p) | each step different, constant msg |
| `ar_ring` | `compute_ar_ring_params` | p−1 | **all steps same config** (cfg=1) |
| `a2a_pairwise` | `compute_a2a_pairwise_params` | p−1 | each step different |
| `a2a_bruck` | `compute_a2a_bruck_params` | log₂(p) | each step different, constant msg |

### 3.2 `paradigm/model_gurobi.py` vs `paradigm/model_pulp.py`

Two parallel MILP formulations with **aligned constraints** but different implementations:

- **Nonlinear terms**: Gurobi version directly writes `t_end[i,j] * u[i,j]` (Gurobi handles binary×continuous internally); PuLP version uses auxiliary variables `v[i,j]`, `w[i,j]` with McCormick linearization.
- **debug_model mode**: Both support a simplified debug model (direct `t_reconf_start[i,j] >= t_end[i-1,j]` instead of `t_prev_end` chain).

### 3.3 `paradigm/solver_wrapper.py` — Unified Solver Interface

Core functions:

- `solve_model()` — supports gurobi / pulp / pulp_gurobi / copt backends
- `get_solution_value()` — unified variable value access (`.X` vs `.varValue`)
- `write_model()` — unified solution writing
- `load_solution()` / `validate_solution()` / `load_and_validate_solution()` — solution loading and validation

### 3.4 `main.py` — Entry Point

Main flow:

1. Parse CLI args → load instance + program config
2. Compute baseline → compute one-shot → compute ideal
3. Select best warm start (baseline vs one-shot)
4. Build MILP model → solve
5. Extract results → fallback to warm start if solver result is worse
6. Plot + save solution files
7. Optional: `debug_mode=1` runs debug model, `debug_mode=2` loads external solution for validation
8. Optional: write metrics JSON

### 3.5 `scripts/` — Batch Experiment Infrastructure

- `generate_matrix_configs.py`: Parse `config/matrix/*.toml` → Cartesian product expansion → instance TOMLs + `index.json`
- `matrix_runner.py`: Read spec → skip completed → invoke `main.py` per config → append to `logs/matrix_results.csv`
- `matrix_archive.py`: Archive run directories/configs to `logs/archive/` by `matrix_id`, optional cleanup

---

## 4. Issues and Code Smells Found

### P1: 🔴 [HIGH] `cc_algorithm.py` ReduceScatter message size calculation bug

**Location**: `config/cc_algorithm.py` L18–23

**Issue**: `compute_rs_having_doubling_params` calls `compute_ag_hd_message_sizes` (AllGather message sizes), but ReduceScatter has its own `compute_rs_hd_message_sizes` function that is **defined but never used**.

**Impact**: ReduceScatter algorithm message sizes may be incorrect.

### P2: 🔴 [HIGH] `solver_wrapper.py` warm_start flag hardcoded to True

**Location**: `paradigm/solver_wrapper.py` L33–34

**Issue**: `warm_start_applied = True  # NOTE: 🚧🚧🚧` — regardless of whether warm start payload exists, `warm_start_applied` is always `True`.

**Impact**: May trigger Gurobi feasibility check or `pulp_gurobi`'s `warmStart=True` when no warm start is present.

### P3: 🔴 [HIGH] `model_gurobi.py` `_validate_solution` uses undefined `T_lat`

**Location**: `paradigm/model_gurobi.py` L241–276

**Issue**: Function body never executes `T_lat = params.get('T_lat', 0)`, but uses `T_lat` in constraint checks.

**Impact**: Calling `_validate_solution` will raise `NameError`.

### P4: 🟡 [MEDIUM] Duplicated validation logic

**Location**: `solver_wrapper.py` and `model_gurobi.py` each have validate/load implementations

**Issues**:

- Different parameter signatures (wrapper has `solver` param, gurobi has `if_debug_model` but no `solver`)
- Different JSON formats (PuLP: `"d_1_1"`, Gurobi: `"d[1,1]"` nested in `Vars` array)
- `main.py` debug_mode calls wrapper version `load_and_validate_solution` with mixed parameters

**Impact**: Maintenance difficulty, logic may diverge.

### P5: 🟡 [MEDIUM] `solver_wrapper.py` `solver` variable name reuse

**Location**: `paradigm/solver_wrapper.py` L81–90

**Issue**: Input string `'pulp'` gets reassigned to PuLP solver object, shadowing the parameter.

**Impact**: Poor readability; using original string later in function would fail.

### P6: 🟡 [MEDIUM] Big-M value not robust enough

**Location**: `paradigm/model_gurobi.py` L19, `paradigm/model_pulp.py`

**Issue**: Uses message size `m` as big-M (`M = params['m']`). PuLP version also has `M_time = 1e6`.

**Impact**: When `m` is very small, big-M constraint may be too tight (though theoretically `d <= m` holds).

### P7: 🟡 [MEDIUM] `main.py` is monolithic

**Issue**: `main()` function is ~150 lines mixing config loading, model building, warm start selection, solving, result comparison, fallback logic, debug mode branching, and metrics writing.

**Impact**: Hard to test and maintain individually.

### P8: 🟢 [LOW] Missing `__init__.py` files

**Location**: `paradigm/`, `config/`, `utils/`

**Issue**: Relies on implicit namespace package discovery (requires `PYTHONPATH=.`).

**Impact**: IDE support may be poor, packaging may miss modules.

### P9: 🟢 [LOW] `one_shot.py` OCS allocation may be uneven

**Location**: `paradigm/one_shot.py`

**Issue**: Uses `math.ceil(k / distinct_configs_num)` for allocation; last group may be under-allocated. Code comment already notes *"This may cause unfairness"*.

### P10: 🟢 [LOW] `baseline.py` lacks cross-step synchronization

**Location**: `paradigm/baseline.py`

**Issue**: Each OCS executes steps independently, no forced sync point ("all OCS finish current step before next step starts").

**Impact**: May be intentional (fastest achievable time), but inconsistent with MILP P3 constraint.

### P11: 🟢 [LOW] Inconsistent logging/output

- `scheduler_analysis.py` uses `print()` instead of `log.info()`
- Some functions use Chinese logs, others English

### P12: 🟢 [LOW] Too many artifacts in `figures/`

`figures/` has **500+** PDF files (excluded by `.gitignore` but accumulates locally).

---

## 5. Code Line Count

| File | Lines | Responsibility |
|------|-------|----------------|
| `main.py` | ~150 | Entry + orchestration |
| `config/instance_parser.py` | ~80 | Parameter parsing |
| `config/cc_algorithm.py` | ~160 | CC algorithm params |
| `paradigm/model_gurobi.py` | ~390 | Gurobi modeling + validation |
| `paradigm/model_pulp.py` | ~140 | PuLP modeling |
| `paradigm/solver_wrapper.py` | ~220 | Unified interface + validation |
| `paradigm/baseline.py` | ~75 | Baseline schedule |
| `paradigm/one_shot.py` | ~80 | One-shot scheme |
| `paradigm/ideal.py` | ~10 | Theoretical lower bound |
| `paradigm/warm_start.py` | ~80 | Warm start conversion |
| `utils/scheduler_analysis.py` | ~180 | Result extraction + plotting |
| `scripts/generate_matrix_configs.py` | ~170 | Matrix config generation |
| `scripts/matrix_runner.py` | ~220 | Batch experiment runner |
| `scripts/matrix_archive.py` | ~130 | Archive cleanup |

**Total core code**: ~2,100 lines Python.

---

## 6. Refactoring Priority

| Priority | Suggestion | Issue | Impact |
|----------|-----------|-------|--------|
| 🔴 HIGH | Fix ReduceScatter message sizes: call `compute_rs_hd_message_sizes` | P1 | Correctness |
| 🔴 HIGH | Fix `warm_start_applied` initial value to `False` | P2 | Correctness |
| 🔴 HIGH | Add `T_lat = params.get('T_lat', 0)` in `_validate_solution` | P3 | Runtime crash |
| 🟡 MEDIUM | Merge duplicate validate/load logic into `solver_wrapper.py` | P4 | Maintainability |
| 🟡 MEDIUM | Split `main.py` into build → solve → analyze → export sub-functions | P7 | Testability |
| 🟡 MEDIUM | Unify logging approach and language | P11 | Consistency |
| 🟡 MEDIUM | Rename `solver` variable to avoid parameter name conflict | P5 | Readability |
| 🟢 LOW | Add `__init__.py` files | P8 | Package import conventions |
| 🟢 LOW | Improve Big-M value selection strategy | P6 | Robustness |
| 🟢 LOW | Review baseline step synchronization semantics | P10 | Semantic consistency |

---

## 7. Recommended Refactoring Path

1. **Phase 1 — Fix Bugs**: Resolve P1, P2, P3 to ensure code runs correctly
2. **Phase 2 — Eliminate Duplication**: Merge validate/load logic (P4), unify solver interface
3. **Phase 3 — Split main.py**: Extract sub-functions for testability (P7)
4. **Phase 4 — Code Standards**: Add `__init__.py` (P8), unify logging (P11), variable naming (P5)
5. **Phase 5 — Robustness**: Big-M strategy (P6), baseline sync semantics (P10), one-shot allocation (P9)
