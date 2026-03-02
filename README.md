# SWOT Scheduler — overlap4ocs

> 由 GPT-5 初步提供。

## 项目简介

`overlap4ocs`（SWOT Scheduler）旨在通过联合优化光学电路交换机（OCS）的重配置与集体通信调度，最小化通信完成时间（CCT）。该项目将通信与重配置问题建模为混合整数线性规划（MILP），并提供基于 Gurobi 与 PuLP 的求解实现，同时包含基线、一次性（one-shot）和理想（ideal）多种对比范式以便评估优化收益。

## 核心思路

- 将每个通信步骤的传输与 OCS 重配置联合建模；
- 通过引入时间变量与二进制变量，保证重配置与传输之间的先后关系和 OCS 不重叠使用的约束（见 `math_model.md`）；
- 使用商用求解器（Gurobi）或开源替代（PuLP）求解 MILP，输出调度并绘制甘特图进行可视化。

## 仓库结构（概要）

- `main.py`：程序入口，负责读取配置、构建模型、求解、提取与绘图并保存结果。

- `config/`：包含 `instance.toml`（实例参数）、`program.toml`（运行配置）及 `instance_parser.py`（解析器）。

  :warning: 注：如 `config/instance.toml`所示，为了能够直接计算 `m/B`、`m_i[i]/B` 和 `d/B`，我们将时间单位固定为毫秒(ms)，将传输单位转换为GBps，并将消息大小设为MB。

- `paradigm/`：调度范式与建模代码（`model_gurobi.py`、`model_pulp.py`、`solver_wrapper.py`、`baseline.py`、`one_shot.py`、`ideal.py`）。

  - 建模：`model_gurobi.py`/`model_pulp.py` 构造决策变量（如数据分配、重配置二进制、起止时间等）与约束，并定义目标最小化 CCT。
  - 求解器封装：`solver_wrapper.py` 提供统一接口：`solve_model`, `get_solution_value`, `write_model`, `load_and_validate_solution`。
  - 对比范式：`baseline.py`（基线策略）、`one_shot.py`（一次性配置方案）、`ideal.py`（理论下界计算）。

- `utils/`：工具函数（例如 `scheduler_analysis.py` 用于抽取求解器结果并绘图）。

  `utils/scheduler_analysis.py` 的 `plot_schedule` 可绘制每步在各 OCS 上的重配置与传输时间线图。

- `figures/`：保存生成的调度图（PDF）。

- `solution/`：保存求解得到的解文件（JSON 或 `.sol`）。

- `math_model.md` 给出了 MILP 的数学描述，包括变量说明与约束（P1：传输-重配置先后；P2：OCS 不重叠活动；P3：步骤间同步）。


## 快速上手
### 使用 uv（推荐，可复现）

1. 安装 uv（macOS 示例）：

  ```bash
  brew install uv
  # 或者使用官方安装脚本/其他包管理器
  ```

2. 创建并同步虚拟环境（默认在仓库内生成 `.venv/`）：

  ```bash
  uv sync
  ```

  - 若需要使用 Gurobi 求解器（可选）：

    ```bash
    uv sync --extra gurobi
    ```

  - 若需要运行 notebook（可选，包含 numpy/pandas/jupyter/ipykernel）：

    ```bash
    uv sync --extra notebook
    ```

3. 运行默认实例：

  ```bash
  uv run python main.py --config config/instance.toml
  ```

4. 运行 `scripts/*.py`（有些脚本依赖仓库内模块导入，建议加上 `PYTHONPATH=.`）：

  ```bash
  PYTHONPATH=. uv run python scripts/<script>.py --help
  ```

### 使用 pip（兼容方式）

如果你不想用 uv，也可以继续使用：

```bash
pip install -r requirements.txt
python3 main.py --config config/instance.toml
```

- 若需要记录一次性运行的指标，可附加 `--metrics-file logs/runs/demo_run_metrics.json --run-id demo-run`（路径可自定义）。

  该命令会在 `logs/runs/` 下写出时间戳、参数、CCT 对比等 JSON 数据，便于后续分析或复现。

3. 常用配置点：

   - `config/program.toml`：`save_as_pdf`、`debug_mode`（0/1/2）、`show`（是否显示图形）等；

   - `config/instance.toml`：`solver`（`gurobi`/`pulp`/`copt`）、`p`（节点数）、`k`（OCS 数量）、`m`（消息大小或各步消息）、`T_reconf`（重配置延迟）以及 `T_lat`（端到端基础时延）等；

   >  若不具备 Gurobi 许可，请将 `solver` 设置为 `pulp` 或`copt`以使用开源或其他求解路径（尽管性能可能略差）。

4. 默认输出位置：

   - 图像：保存在 `figures/`，文件名类似 `figures/solution_*.pdf`；

   - 解文件：保存在 `solution/`，文件名类似 `solution/solution_*.json`。


## 进阶：批量实验（自动配置 + 全局日志）

- **使用 `config/matrix/*.toml` 描述参数矩阵**

  例如 `config/matrix/example_matrix.toml` 指定 `matrix_id`、拓扑 (`k,p,B,T_reconf,T_lat`)、算法列表与消息大小列表，并声明统一的 `solver`、`program_config` 以及输出目录。

- **运行配置生成器**：
  
  ```bash
  PYTHONPATH=. uv run python scripts/generate_matrix_configs.py --matrix config/matrix/example_matrix.toml
  ```
  
  会把所有组合写入 `logs/generated_configs/<matrix_id>/`，并生成 `index.json` 记录哈希，方便后续 resume。
  
- **启动批量求解实验**：

  ```bash
  PYTHONPATH=. uv run python scripts/matrix_runner.py --matrix config/matrix/example_matrix.toml
  ```

  - 运行器会对未完成的配置逐一求解，并为每次实验创建 `logs/runs/<run-id>/` 目录（包含 `config/`、`figures/`、`solution/`、`run.log`、`metrics.json`、`metadata.json`）。可用 `--limit`, `--rerun-failed`, `--extra-args` 等参数细分批次、透传额外选项。
  - 每次运行结束后追加一行到 `logs/matrix_results.csv`（字段包含时间戳、 matrix_id、算法、消息大小、网络参数、集群规模、求解耗时、CCT/基线/理想值、改进百分比以及 `metrics.json` 路径），供后续分析、绘图直接读取。
  - 示例命令（无 `--limit`）已完成整个 `ar_k2_p8_sweep`，所有衍生 run 目录位于 `logs/runs/20251129-16xxxx_*`。

- Notebook 侧可直接加载 `logs/matrix_results.csv` 构建 DataFrame，筛选任意拓扑 + 算法子集并绘图，无需再手动查找单个 `metrics.json`。

- 需要释放空间时，可使用：

  ```bash
  uv run python scripts/matrix_archive.py --matrix-id <name> [--cleanup]
  ```

## Notebook（Jupyter / VS Code）

本仓库包含：

- `notebook/*.ipynb`
- `scripts/*.ipynb`

建议用 uv 安装 notebook 依赖：

```bash
uv sync --extra notebook
```

### 在 VS Code 中使用 Jupyter

1. 先完成 `uv sync`（以及需要的话 `uv sync --extra notebook`）。
2. 打开 VS Code 命令面板，选择 **Python: Select Interpreter**，选中仓库内的解释器：`.venv/bin/python`。
3. 打开任意 `.ipynb` 文件，在右上角选择 Kernel，选择与 `.venv` 对应的 Python 环境。

如果 VS Code 没有自动识别内核，可执行一次：

```bash
uv run python -m ipykernel install --user --name overlap4ocs --display-name "overlap4ocs (.venv)"
```

  将指定矩阵的 run 目录与配置拷贝至 `logs/archive/` 并（可选）从生产目录及 `logs/matrix_results.csv` 中移除，实现“归档 + 按矩阵清理”。



## 常见问题与注意事项

- 可扩展性：随着 `p` 或 `k` 增大，MILP 求解时间会显著增加，建议先用小规模参数测试或使用。
- 输入一致性：确保 `config/instance.toml` 中字段与 `instance_parser.py` 的预期格式一致。