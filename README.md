# SWOT Scheduler — overlap4ocs

> 由 GPT-5 提供。

## 项目简介

`overlap4ocs`（SWOT Scheduler）旨在通过联合优化光学电路交换机（OCS）的重配置与集体通信调度，最小化通信完成时间（CCT）。该项目将通信与重配置问题建模为混合整数线性规划（MILP），并提供基于 Gurobi 与 PuLP 的求解实现，同时包含基线、一次性（one-shot）和理想（ideal）多种对比范式以便评估优化收益。

## 核心思路

- 将每个通信步骤的传输与 OCS 重配置联合建模；
- 通过引入时间变量与二进制变量，保证重配置与传输之间的先后关系和 OCS 不重叠使用的约束（见 `math_model.md`）；
- 使用商用求解器（Gurobi）或开源替代（PuLP）求解 MILP，输出调度并绘制甘特图进行可视化。

## 仓库结构（概要）

- `main.py`：程序入口，负责读取配置、构建模型、求解、提取与绘图并保存结果。
- `config/`：包含 `instance.toml`（实例参数）、`program.toml`（运行配置）及 `instance_parser.py`（解析器）。
- `paradigm/`：调度范式与建模代码（`model_gurobi.py`、`model_pulp.py`、`solver_wrapper.py`、`baseline.py`、`one_shot.py`、`ideal.py`）。
- `utils/`：工具函数（例如 `scheduler_analysis.py` 用于抽取求解器结果并绘图）。
- `figures/`：保存生成的调度图（PDF）。
- `solution/`：保存求解得到的解文件（JSON 或 `.sol`）。
- `math_model.md`：对 MILP 模型、变量与约束的数学描述（包括 P1–P3 三个重要性质）。

## 关键模块说明

- 建模：`model_gurobi.py`/`model_pulp.py` 构造决策变量（如数据分配、重配置二进制、起止时间等）与约束，并定义目标最小化 CCT。
- 求解器封装：`solver_wrapper.py` 提供统一接口：`solve_model`, `get_solution_value`, `write_model`, `load_and_validate_solution`。
- 对比范式：`baseline.py`（基线策略）、`one_shot.py`（一次性配置方案）、`ideal.py`（理论下界计算）。
- 可视化：`utils/scheduler_analysis.py` 的 `plot_schedule` 可绘制每步在各 OCS 上的重配置与传输时间线图。

## 使用说明（快速上手）

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 运行默认实例（macOS / zsh）：

```bash
python3 main.py --config config/instance.toml
```

3. 常用配置点：

- `config/program.toml`：`save_as_pdf`、`debug_mode`（0/1/2）、`show`（是否显示图形）等；
- `config/instance.toml`：`solver`（`gurobi`/`pulp`/`copt`）、`p`（节点数）、`k`（OCS 数量）、`m`（消息大小或各步消息）、`T_reconf`（重配置延迟）以及 `T_lat`（端到端基础时延）等；
- 若不具备 Gurobi 许可，请将 `solver` 设置为 `pulp` 以使用开源求解路径（尽管性能可能较差）。

4. 输出位置：

- 图像：保存在 `figures/`，文件名类似 `figures/solution_*.pdf`；
- 解文件：保存在 `solution/`，文件名类似 `solution/solution_*.json`。

## 论文/模型关联

- `math_model.md` 给出了 MILP 的数学描述，包括变量说明与约束（P1：传输-重配置先后；P2：OCS 不重叠活动；P3：步骤间同步）。该模型直接对应 `paradigm/model_gurobi.py` 的实现。

## 常见问题与注意事项

- Gurobi：若选择 `gurobi`，需在系统中安装 Gurobi 并配置许可；否则使用 `pulp`。
- 可扩展性：随着 `p` 或 `k` 增大，MILP 求解时间会显著增加，建议先用小规模参数测试或使用 `debug_mode`。
- 输入一致性：确保 `config/instance.toml` 中字段与 `instance_parser.py` 的预期格式一致。

## 后续建议

- 将本文件补充为更详细的 `README`（如示例实例、图示说明、性能基准）；
- 增加示例 `instance.toml` 与小型测试用例；
- 添加单元测试与 CI（使用 `pulp` 模式在 CI 中避免 Gurobi 许可问题）；
- 提供启发式近似算法以支持更大规模实例的快速求解。


# TODO: 
1. requirements.txt
2. debug mode test
3. mkdir