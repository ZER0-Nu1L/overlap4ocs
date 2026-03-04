# 矩阵实验基础设施

本文档解释矩阵实验自动化工具链的工作方式，并说明如何在新增场景或参数组合时扩展它。

## 设计目标

- **覆盖参数空间**：一次性声明拓扑、算法、消息大小的大型组合，让脚本自动遍历。
- **确定性复现**：可随时重新生成同样的 `instance.toml` 文件，并仅 rerun 感兴趣的子集，无需手改配置。
- **完整留存**：统一使用 `logs/runs/<run-id>/` 结构保存图像、解文件、配置、日志与指标，确保可追溯。
- **统一分析**：每个矩阵按 spec 中的 `output.results_csv` 追加写入，后续可由 `scripts/prepare_simulation_data.py` 聚合为论文绘图 CSV。

## 矩阵配置（`config/matrix/*.toml`）

每个矩阵是一个独立的 TOML 文件，推荐结构如下（详见 `config/matrix/example_matrix.toml`）：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `matrix_id` | ✔ | 唯一 ID，同时用作生成配置文件、CSV 标签的前缀。 |
| `solver` | ✖（默认为 `pulp`） | 所有实例共享的求解器。 |
| `program_config` | ✖ | 运行时要快照的 `program.toml` 路径。 |
| `message_sizes_mib` | ✔ | 消息大小数组（MiB），生成时转换为字节填入 `m`。 |
| `algorithms` | ✔ | 算法名称列表（`ar_having-doubling`、`a2a_pairwise`、`a2a_bruck` 等）。 |
| `[topology]` | ✔ | 子表，包含 `k`、`p`、`B`、`T_reconf`、`T_lat` 等拓扑参数。请确保单位与模型一致（当前 `B` 按字节/毫秒）。 |
| `[output]` | ✖ | 输出配置，可指定 `config_dir`（生成文件目录）、`results_csv`（全局日志）、`runs_root`（run 目录，默认 `logs/runs`）。 |

一个仓库中可并存多个 spec，只要各自的 `matrix_id` 区分即可共享输出目录。

## 阶段一：生成实例 (`scripts/generate_matrix_configs.py`)

示例命令：

```bash
PYTHONPATH=.  python scripts/generate_matrix_configs.py --matrix config/matrix/example_matrix.toml
```

流程：

1. 解析矩阵 spec 并校验必填字段。
2. 把所有组合写入 `logs/generated_configs/<matrix_id>/`，文件名可直接看出算法/消息大小，例如 `ar_k2_p16_sweep_ar_having-doubling_m000032.toml`。
3. 在同目录生成 `index.json`，记录每个配置的路径、算法、消息大小、solver 以及实例内容的 SHA1，用于去重/恢复。
4. 若未加 `--overwrite`，遇到已有文件会报错，避免无意覆盖已验证的配置。

随时可以以同样命令 + `--overwrite` 重建配置（例如修改 spec 后）。矩阵运行器会优先读取 `index.json`，若缺失再自动触发生成。

## 阶段二：矩阵运行器 (`scripts/matrix_runner.py`)

示例命令（完整 sweep）：

```bash
PYTHONPATH=. python scripts/matrix_runner.py --matrix config/matrix/example_matrix.toml
```

关键特性：

1. 读取 spec 并确保配置存在（若加 `--regenerate` 则强制重建）。
2. 结合目标 `results_csv` 的哈希，计算待运行列表；默认跳过已成功完成的条目，可用 `--no-resume` 关闭、`--rerun-failed` 只重跑失败项。
3. 对每个待运行的配置调用内置的 `run_experiment`，自动完成日志、指标、文件拷贝等 run 级别记录。
4. 每次运行结束即向 CSV 追加一行，字段包含时间、matrix_id、算法、消息大小、solver、耗时、求解状态、各类 CCT、相对提升、`metrics.json` 路径以及配置哈希。
5. 提供控制/恢复选项：
   - `--limit N`：本次只执行前 N 个待运行条目，适合分批跑大矩阵。
   - `--extra-args "--program-config ..."`：将任意参数透传给 `main.py`。
   - `--dry-run`：仅创建 run 目录，不实际执行（调试排期 ID 时有用）。

脚本会持续输出 `[RUN i/N] ... -> status=...`，末尾给出执行统计。

## 数据产物

单次 run 的目录结构：

```
logs/runs/<run-id>/
  |- config/                 # instance + program 配置快照
  |- figures/                # 结果图 PDF（solution/baseline/oneshot）
  |- solution/               # 对应 JSON 解文件
  |- logs/run.log            # 主程序+求解器输出
  |- metrics.json            # main.py 写入的指标/路径摘要
   |- metadata.json           # matrix_runner 记录的命令、git 信息、耗时
```

结果 CSV（路径由每个 spec 的 `output.results_csv` 决定）：追加式日志。Notebook 或绘图脚本可按 `matrix_id`、`algorithm`、`message_mib` 过滤分析。由于每行包含 `metrics.json` 的绝对路径，深入挖掘单个 run 时仍可直接定位。

## 推荐流程

1. 在 `config/matrix/` 新建或编辑一个 spec。
2. 生成实例：
   ```bash
   PYTHONPATH=. python scripts/generate_matrix_configs.py --matrix config/matrix/new_spec.toml --overwrite
   ```
3. 分批或一次性执行：
   ```bash
   PYTHONPATH=. python3 scripts/matrix_runner.py --matrix config/matrix/new_spec.toml --limit 10
   ```
4. 通过对应 `results_csv`、`logs/runs/<run-id>/metrics.json` 或 `scripts/simulation_fig.ipynb` 查看结果；需要论文级聚合时运行 `scripts/prepare_simulation_data.py`。
5. 如需继续，直接再次运行矩阵脚本，默认会跳过已成功的组合；若需重跑失败项，使用 `--rerun-failed`。

## 后续扩展建议

- **多拓扑组合**：扩展 spec 以支持多个 `[topology]` 块并求笛卡尔积。
- **并行执行**：用 worker pool 包装 `run_experiment`，压榨多核或远端节点。
- **富指标**：当 `main.py` 输出更多字段时，把 solver gap、迭代次数、图像路径等写入 CSV。
- **自动分析**：新增 `scripts/matrix_analyze.py`，读取 CSV 后输出标准化图表或报告。
- **CI 回归**：挑选小规模矩阵跑 nightly，比较 CSV 以监控性能回退。
- **归档/清理**：通过 `scripts/matrix_archive.py --matrix-id <id> --cleanup`，将目标矩阵的 run 目录、生成配置和 CSV 行打包到 `logs/archive/`，并可选择从活跃目录移除，方便释放磁盘或发布离线报告。

希望本文档能提供足够的上下文，帮助你快速修改参数、添加新 sweep，或在其他范式中复用同样的自动化框架。
