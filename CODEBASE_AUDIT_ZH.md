# 代码库审计报告 — overlap4ocs (SWOT Scheduler)

> 审计时间：2025 年  
> 审计范围：除 `logs/` 和 `archives/` 外的全部源码

---

## 1. 项目定位

**SWOT Scheduler (overlap4ocs)** —— 通过 MILP（混合整数线性规划）联合优化 OCS（光电路交换机）重配置与集体通信调度，最小化 CCT（通信完成时间）。支持多种集体通信算法：

- AllReduce: ring / halving-doubling / recursive-doubling
- All-to-All: pairwise / bruck
- ReduceScatter / AllGather: halving-doubling

---

## 2. 模块依赖关系图

```
main.py  (入口)
├── config/instance_parser.py    → 读 TOML、校验参数
│   └── config/cc_algorithm.py   → 计算算法特定参数 (num_steps, m_i, configurations)
├── paradigm/baseline.py         → 基线调度（无优化）
├── paradigm/one_shot.py         → 一次性 OCS 预配置
├── paradigm/ideal.py            → 理论下界
├── paradigm/warm_start.py       → 将 baseline/oneshot 转为 warm start
├── paradigm/model_gurobi.py     → Gurobi MILP 建模
├── paradigm/model_pulp.py       → PuLP MILP 建模
├── paradigm/solver_wrapper.py   → 统一求解接口 + 解验证
└── utils/scheduler_analysis.py  → 结果提取 + 甘特图绘制
    └── utils/check_platform.py  → ARM Mac 检测

scripts/
├── generate_matrix_configs.py   → 矩阵参数展开 → 生成 instance.toml
├── matrix_runner.py             → 批量实验 → 结果追加至 CSV
└── matrix_archive.py            → 归档/清理实验产物
```

---

## 3. 各模块详细梳理

### 3.1 `config/cc_algorithm.py` — 集体通信算法参数

| 算法 | 函数 | num_steps | 配置特征 |
|------|------|-----------|----------|
| `rs_having-doubling` | `compute_rs_having_doubling_params` | log₂(p) | 每步配置不同 |
| `ag_having-doubling` | `compute_ag_having_doubling_params` | log₂(p) | 每步配置不同 |
| `ar_having-doubling` | `compute_ar_having_doubling_params` | 2×log₂(p) | 前后对称配置 |
| `ar_recursive-doubling` | `compute_ar_recursive_doubling_params` | log₂(p) | 每步配置不同，消息大小恒定 |
| `ar_ring` | `compute_ar_ring_params` | p-1 | **所有步配置相同** (cfg=1) |
| `a2a_pairwise` | `compute_a2a_pairwise_params` | p-1 | 每步配置不同 |
| `a2a_bruck` | `compute_a2a_bruck_params` | log₂(p) | 每步配置不同，消息大小恒定 |

### 3.2 `paradigm/model_gurobi.py` vs `paradigm/model_pulp.py` — 两套并行 MILP 建模

两者约束逻辑**基本对齐**，但实现方式有差异：

- **非线性项处理**：Gurobi 版直接写 `t_end[i,j] * u[i,j]`（Gurobi 可内部处理 binary×continuous）；PuLP 版用辅助变量 `v[i,j]`、`w[i,j]` 做 McCormick 线性化。
- **debug_model 模式**：两者都支持一个简化的 debug 模型（直接用 `t_reconf_start[i,j] >= t_end[i-1,j]` 代替 `t_prev_end` 链）。
- 约束编号 (1)–(10) 与 `math_model.md` 中的公式 (1)–(16) 对应。

### 3.3 `paradigm/solver_wrapper.py` — 统一求解接口

核心函数：
- `solve_model()` — 支持 gurobi / pulp / pulp_gurobi / copt 四种后端
- `get_solution_value()` — 统一取变量值 (`.X` vs `.varValue`)
- `write_model()` — 统一写解
- `load_solution()` / `validate_solution()` / `load_and_validate_solution()` — 解文件加载与验证

### 3.4 `main.py` — 程序主入口

主流程：
1. 解析 CLI 参数 → 加载 instance + program 配置
2. 计算 baseline → 计算 one-shot → 计算 ideal
3. 选最优 warm start (baseline vs one-shot)
4. 构建 MILP 模型 → 求解
5. 提取结果 → 如果 solver 结果差于 warm start 则回退
6. 绘图 + 保存解文件
7. 可选：debug_mode=1 跑 debug 模型，debug_mode=2 加载外部解验证
8. 可选：写 metrics JSON

### 3.5 `utils/scheduler_analysis.py` — 结果提取 + 甘特图

- `extract_results()` — 从 solver 模型对象提取调度记录（支持 Gurobi 和 PuLP）
- `apply_offset()` — 时间偏移（扣除第一轮重配置）
- `plot_schedule()` — 绘制甘特图，展示每个 OCS 上的 reconf/latency/transmission 时间块

### 3.6 `scripts/` — 批量实验工具链

| 脚本 | 功能 |
|------|------|
| `generate_matrix_configs.py` | 从 `config/matrix/*.toml` 展开参数笛卡尔积，生成 instance.toml + index.json |
| `matrix_runner.py` | 遍历待运行配置，调用 `main.py`，收集 metrics，追加到 `logs/matrix_results.csv` |
| `matrix_archive.py` | 按 matrix_id 归档 run 目录/配置/CSV 行，并可选清理 |

---

## 4. 代码行数统计

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | ~150 | 入口+编排 |
| `config/instance_parser.py` | ~80 | 参数解析+校验 |
| `config/cc_algorithm.py` | ~160 | CC 算法参数计算 |
| `paradigm/model_gurobi.py` | ~390 | Gurobi 建模+验证 |
| `paradigm/model_pulp.py` | ~140 | PuLP 建模 |
| `paradigm/solver_wrapper.py` | ~220 | 统一接口+验证 |
| `paradigm/baseline.py` | ~75 | 基线调度 |
| `paradigm/one_shot.py` | ~80 | 一次性方案 |
| `paradigm/ideal.py` | ~10 | 理论下界 |
| `paradigm/warm_start.py` | ~80 | Warm start 转换 |
| `utils/scheduler_analysis.py` | ~180 | 结果提取+绘图 |
| `utils/check_platform.py` | ~15 | 平台检测 |
| `scripts/generate_matrix_configs.py` | ~170 | 矩阵配置生成 |
| `scripts/matrix_runner.py` | ~220 | 批量实验运行 |
| `scripts/matrix_archive.py` | ~130 | 归档清理 |

**核心代码量**：约 **2,100 行** Python。

---

## 5. 🐛 已发现的问题与代码坏味道

### P1: `cc_algorithm.py` 存在 Bug — ReduceScatter 消息大小计算错误

**严重度**：🔴 高（影响正确性）  
**位置**：`config/cc_algorithm.py` L18–23

```python
def compute_rs_having_doubling_params(p, m):
    ...
    return {
        ...
        'm_i': compute_ag_hd_message_sizes(m, num_steps),  # ← 调用了 AllGather 的函数！
        'configurations': compute_ag_hd_configurations(num_steps),
    }
```

`compute_rs_hd_message_sizes()` 已定义（L26–30）但**从未被调用**。ReduceScatter 的消息大小应该是 `m / (2^i)` 递减，而 AllGather 是反向的。

---

### P2: `solver_wrapper.py` warm_start 标志硬编码为 True

**严重度**：🔴 高（影响正确性）  
**位置**：`paradigm/solver_wrapper.py` L33–34

```python
def solve_model(...):
    warm_start_applied = True  # NOTE: 🚧🚧🚧
```

无论是否实际有 warm start payload，`warm_start_applied` 始终为 `True`。这导致：
- Gurobi 路径中会无条件执行 `feasRelaxS` 检查
- `pulp_gurobi` 路径中 `warmStart=True` 无条件传入
- 返回值始终声称 warm start 已应用

**应修复为**：`warm_start_applied = False`，仅在 `apply_warm_start` 成功后才置 `True`。

---

### P3: `model_gurobi.py` 中 `_validate_solution` 使用了未定义的 `T_lat`

**严重度**：🔴 高（运行时会 NameError）  
**位置**：`paradigm/model_gurobi.py` L241–276

```python
def _validate_solution(params, d, t_start, t_end, u, r, ...):
    k = params['k']
    num_steps = params['num_steps']
    m_i = params['m_i']
    B = params['B']
    T_reconf = params['T_reconf']
    configurations = params['configurations']
    # ← 缺少 T_lat = params.get('T_lat', 0)
    ...
    # L~276:
    if abs((t_end[i, j] - t_start[i, j]) - (d[i, j] / B + T_lat * u[i, j])) > epsilon:
```

`T_lat` 在此函数中从未提取 `params`，调用时会崩溃。

---

### P4: 重复的验证逻辑

**严重度**：🟡 中（可维护性）

`solver_wrapper.py` 和 `model_gurobi.py` 各自有一套完整的：
- `load_solution` / `_load_solution`
- `validate_solution` / `_validate_solution`
- `load_and_validate_solution`

它们之间的差异：

| 方面 | `solver_wrapper.py` | `model_gurobi.py` |
|------|---------------------|-------------------|
| JSON 格式 | PuLP 风格：`"d_1_1"` | Gurobi 风格：`"d[1,1]"` 嵌套在 `Vars` 数组 |
| 函数签名 | 有 `solver` 参数 | 有 `if_debug_model` 但无 `solver` |
| T_lat 处理 | ✅ 正确 | ❌ Bug (P3) |

建议：合并为单一验证模块，根据 solver 类型自动检测 JSON 格式。

---

### P5: `solver_wrapper.py` 中 `solver` 变量名复用

**严重度**：🟢 低（可读性）  
**位置**：`paradigm/solver_wrapper.py` L81–90

```python
elif solver == 'pulp':  # solver 是字符串 'pulp'
    ...
    if check_platform.is_arm_mac():
        solver = pulp.getSolver(...)  # solver 被赋值为 PuLP solver 对象！
    else:
        solver = pulp.PULP_CBC_CMD(...)
    model.solve(solver)
```

函数参数 `solver` (字符串) 被覆盖为 solver 对象。虽然后续不再使用，但可读性差、容易引入隐患。建议重命名为 `solver_instance`。

---

### P6: Big-M 值选择不够健壮

**严重度**：🟢 低（健壮性）  
**位置**：`paradigm/model_gurobi.py` L19, `paradigm/model_pulp.py` L14

```python
M = params['m']  # Large constant value for big-M method
```

使用消息大小 `m` 作为 big-M。对于约束 `d[i,j] <= u[i,j] * M`，这实际上是正确的（d 不会超过 m）。但名称 `M` 容易与数学文献中的"大 M"概念混淆。PuLP 版本额外定义了 `M_time = 1e6` 用于时间相关约束。

建议：使用更明确的命名（如 `M_data = m`, `M_time = 1e6`）。

---

### P7: `main.py` 过于臃肿

**严重度**：🟡 中（可维护性/可测试性）

`main()` 函数约 150 行，混合了以下职责：
- 配置读取与文件路径构造
- 模型构建与求解
- Warm start 选择逻辑
- 结果对比与 fallback
- Debug 模式分支
- Metrics 写入

建议拆分为独立函数：
- `build_and_solve(params, warm_start_payload) → schedule, cct`
- `compare_results(cct_optimized, cct_baseline, cct_oneshot, cct_ideal) → metrics`
- `export_results(schedule, metrics, paths)`

---

### P8: 缺少 `__init__.py`

**严重度**：🟢 低（包导入规范）

`paradigm/`、`config/`、`utils/` 目录均无 `__init__.py`，依赖隐式命名空间包（需要 `PYTHONPATH=.`）。建议添加空的 `__init__.py` 以明确包边界。

---

### P9: `one_shot.py` 中 OCS 分配可能不均

**严重度**：🟢 低（公平性）  
**位置**：`paradigm/one_shot.py` L14–17

```python
d = math.ceil(k / distinct_configs_num)
```

当 `k` 不是 `distinct_configs_num` 的倍数时，最后一组 OCS 可能分配不足。代码中已有注释 "This may cause unfairness"。

---

### P10: `baseline.py` 缺少步骤间同步

**严重度**：🟡 中（语义一致性）  
**位置**：`paradigm/baseline.py`

Baseline 中每个 OCS 独立执行各步，**没有**强制"所有 OCS 完成当前步再开始下一步"的同步约束（P3）。这与 MILP 模型中的步骤同步约束不一致。

需要确认：这是有意为之（展示最快可达时间）还是应该添加同步？如果不同步，则 baseline CCT 可能偏低，使得 "improvement_over_baseline" 偏保守。

---

### P11: 日志和输出不一致

**严重度**：🟢 低（一致性）

- `scheduler_analysis.py` L51：`print("Pulp solver status:", ...)` 应该用 `log.info()`
- 部分日志中文、部分英文（`solver_wrapper.py` 中文，`model_gurobi.py` 英文）
- `scheduler_analysis.py` L38 中重复 `import logging as log`（函数内部）

---

### P12: 生成的 figures 数量过大

**严重度**：🟢 低（项目整洁）

`figures/` 目录下有 **500+ PDF** 文件在本地积累。虽然 `.gitignore` 排除了，但本地开发时占据大量磁盘。建议定期清理或在 matrix runner 中将产物直接放入 run 目录。

---

## 6. 重构建议优先级

| 优先级 | 编号 | 建议 | 类型 |
|--------|------|------|------|
| 🔴 高 | P1 | 修复 `cc_algorithm.py` ReduceScatter 函数调用 bug | 正确性 |
| 🔴 高 | P2 | 修复 `solver_wrapper.py` warm_start_applied 硬编码 | 正确性 |
| 🔴 高 | P3 | 修复 `model_gurobi.py` `_validate_solution` 中 T_lat 未定义 | 正确性 |
| 🟡 中 | P4 | 合并重复的 validate/load 逻辑到 `solver_wrapper.py` | 可维护性 |
| 🟡 中 | P7 | 拆分 `main.py` 为 build → solve → analyze → export | 可测试性 |
| 🟡 中 | P10 | 确认 baseline 是否应添加步骤同步 | 语义一致性 |
| 🟡 中 | P11 | 统一日志方式（全部使用 `logging`）和语言 | 一致性 |
| 🟢 低 | P5 | 重命名 `solver` 变量避免复用 | 可读性 |
| 🟢 低 | P6 | 改进 Big-M 命名和取值策略 | 健壮性 |
| 🟢 低 | P8 | 添加 `__init__.py` 文件 | 包导入规范 |
| 🟢 低 | P9 | 改进 one-shot OCS 分配逻辑 | 公平性 |
| 🟢 低 | P12 | 清理 figures 积累或改变输出目录策略 | 项目整洁 |

---

## 7. 推荐重构路径

### 阶段一：修复 Bug（P1, P2, P3）

最小改动，确保现有功能正确。

### 阶段二：消除重复（P4）

将 `model_gurobi.py` 中的 `_load_solution`、`_validate_solution`、`load_and_validate_solution` 统一迁移到 `solver_wrapper.py`，并根据 solver 类型自动检测 JSON 格式。删除 `model_gurobi.py` 中的冗余代码。

### 阶段三：拆分入口（P7）

将 `main.py` 拆分为：
- `main.py` — 仅做 CLI 解析和编排
- `pipeline.py` 或类似模块 — 包含 `run_pipeline(params, program_config)` 等可复用函数

### 阶段四：规范化（P5, P6, P8, P11）

---

## 7. 推荐重构路径

1. **阶段一 — 修复 Bug**：解决 P1、P2、P3 以确保代码正确运行
2. **阶段二 — 消除重复**：合并验证/加载逻辑 (P4)，统一求解器接口
3. **阶段三 — 拆分 main.py**：提取子函数以提高可测试性 (P7)
4. **阶段四 — 代码规范**：添加 `__init__.py` (P8)，统一日志记录 (P11)，变量命名 (P5)
5. **阶段五 — 健壮性**：Big-M 策略 (P6)，baseline 同步语义 (P10)，一次性分配 (P9)
