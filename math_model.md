## SWOT Scheduler {#sec:schedule}

The scheduler is the core component of **SWOT**, and the scheduling decisions determine the extent of performance improvement that SWOT can achieve.  
We aim to jointly optimize collective communication with the reconfiguration of Optical Circuit Switches (OCSs) in a systematic way.  

We formulate the overlapping reconfiguration and communication problem as a **Mixed Integer Linear Programming (MILP)** model to **minimize the Communication Completion Time (CCT)**.  

Our model considers:
- $ p $ compute nodes,
- $ k $ OCSes,
- collective communication patterns (e.g., AllReduce using Rabenseifner’s algorithm), where each communication step $ i $ has:
  - message size $ m_i $,
  - required topology configuration $ \text{cfg}_i $.

A legitimate scheduling strategy must satisfy the following three properties:

1. **(P1) Transmission–reconfiguration precedence**:  
   Data transmission starts only after the necessary optical reconfigurations are complete.

2. **(P2) No overlapping activity on OCS**:  
   An OCS cannot perform two activities (e.g., two reconfigurations or a reconfiguration and transmission) simultaneously.

3. **(P3) Cross-step synchronization**:  
   Each communication step begins only after the previous step finishes.

---

### Summary of Key Notations

| Symbol | Type | Description |
|--------|------|-------------|
| **Decision Variables** |||
| $d_{i,j}$ | $\mathbb{R}^+$ | Data volume assigned to OCS $j$ at step $i$ |
| $u_{i,j}$ | $\{0,1\}$ | 1 if OCS $j$ is used at step $i$, 0 otherwise |
| $r_{i,j}$ | $\{0,1\}$ | 1 if OCS $j$ is reconfigured at step $i$ |
| $t_{\text{start}_{i,j}}$ | $\mathbb{R}^+$ | Transmission start time on OCS $j$ at step $i$ |
| $t_{\text{end}_{i,j}}$ | $\mathbb{R}^+$ | Transmission end time on OCS $j$ at step $i$ |
| $t_{\text{recfg\_s}_{i,j}}$ | $\mathbb{R}^+$ | Reconfiguration start time for OCS $j$ at step $i$ |
| $t_{\text{recfg\_e}_{i,j}}$ | $\mathbb{R}^+$ | Reconfiguration end time for OCS $j$ at step $i$ |
| $t_{\text{step\_e}_i}$ | $\mathbb{R}^+$ | Completion time of communication step $i$ |
| $\text{CCT}$ | $\mathbb{R}^+$ | Overall communication completion time (objective) |
| **Intermediate Variables** |||
| $t_{\text{prev\_e}_{i,j}}$ | $\mathbb{R}^+$ | Last completion time of previous activities (transmission or reconfiguration) on OCS $j$ before step $i$ |
| $s_{i,j}$ | $\{0,1\}$ | 1 if OCS $j$’s current configuration matches $\text{cfg}_i$ (used conceptually; implemented by checking $\text{cfg}_i$ vs $\text{cfg}_{i-1}$ in code) |
| **Parameters** |||
| $m_i$ | $\mathbb{R}^+$ | Total data volume required at step $i$ |
| $B$ | $\mathbb{R}^+$ | OCS port bandwidth (e.g., in Gbps) |
| $T_{\text{recfg}}$ | $\mathbb{R}^+$ | OCS reconfiguration latency |
| $T_{\text{lat}}$ | $\mathbb{R}^+$ | Per-transmission base latency (end-to-end cost) |
| $M$ | $\mathbb{R}^+$ | Large constant for big-M method [@cococcioniBigMMethodNumerical2021] |
| $\text{cfg}_i$ | $\mathbb{N}$ | Required topology configuration at step $i$ |

> 💡 **Note on notation**:  
> - Subscripts $i$ and $j$ denote communication step and OCS index, respectively.  
> - Binary variables ($\{0,1\}$) enable logical conditions in the MILP.  
> - The big-$M$ method is used to linearize conditional constraints (e.g., “if configuration changes, then reconfigure”).

---

### Problem Formulation

Our goal is to minimize the overall Communication Completion Time (CCT):

$$
\min \quad \text{CCT}
$$

Subject to the following constraints (for all steps $i$ and OCSes $j$):

$$
\begin{aligned}
		\text{(1)}\quad & \sum_{j=1}^{k} d_{i,j} = m_i \\
		\text{(2)}\quad & t_{\text{end}_{i,j}} - t_{\text{start}_{i,j}} = \dfrac{d_{i,j}}{B} + T_{\text{lat}} \cdot u_{i,j} \\
		\text{(3)}\quad & d_{i,j} \le M \cdot u_{i,j} \\
		\text{(4)}\quad & t_{\text{recfg\_e}_{i,j}} - t_{\text{recfg\_s}_{i,j}} = r_{i,j} \cdot T_{\text{recfg}} \\
		\text{(5)}\quad & t_{\text{start}_{i,j}} \geq t_{\text{recfg\_e}_{i,j}} \\
		\text{(6)}\quad & r_{i,1} \ge u_{i,1} \quad (i = 1) \\
		\text{(7)}\quad & r_{i,j} \ge u_{i,j} - s_{i,j} \quad (i > 1) \\
		\text{(8)}\quad & u_{i,j} \ge r_{i,j} \\
		\text{(9)}\quad & t_{\text{prev\_e}_{1,j}} = 0 \\
		\text{(10)}\quad & t_{\text{prev\_e}_{i,j}} \ge t_{\text{prev\_e}_{i-1,j}} \quad (i > 1) \\
		\text{(11)}\quad & t_{\text{prev\_e}_{i,j}} \ge t_{\text{end}_{i-1,j}} \cdot u_{i-1,j} \quad (i > 1) \\
		\text{(12)}\quad & t_{\text{prev\_e}_{i,j}} \ge t_{\text{recfg\_e}_{i-1,j}} \cdot r_{i-1,j} \quad (i > 1) \\
		\text{(13)}\quad & t_{\text{recfg\_s}_{i,j}} \ge t_{\text{prev\_e}_{i,j}} \\
		\text{(14)}\quad & t_{\text{step\_e}_i} \ge t_{\text{end}_{i,j}} \cdot u_{i,j} \\
		\text{(15)}\quad & t_{\text{start}_{i,j}} \ge t_{\text{step\_e}_{i-1}} \quad \text{for } i > 1 \\
		\text{(16)}\quad & \text{CCT} \ge t_{\text{step\_e}_i} \quad \forall i \\
\end{aligned}
$$

**Explanation of constraints (aligned with `model_gurobi.py` / `model_pulp.py`):**

- **(1)** 总数据量约束：每个步骤 $i$ 在所有 OCS 上发送的数据总量等于 $m_i$。
- **(2)** 带宽+时延约束：传输时长等于“数据量除以带宽 $B$”与固定端到端时延 $T_{\text{lat}}$ 之和（当 $u_{i,j}=1$ 时生效）。
- **(3)** 使用指示变量约束：只有当 $u_{i,j}=1$ 时，$d_{i,j}$ 才能为正；否则被 big-$M$ 约束为 0。
- **(4)** 重配置时长：当且仅当 $r_{i,j}=1$ 时，重配置持续 $T_{\text{recfg}}$ 时间。
- **(5)** **(P1)** 先重配置后传输：传输开始时间不早于重配置结束时间。
- **(6)**–**(8)** 配置变化与使用逻辑：
   - 第一步默认需要重配置（$r_{1,j} \ge u_{1,j}$）。
   - 后续步骤中，如果当前拓扑与上一步不同且该 OCS 被使用（由代码根据 $\text{cfg}_i$、$\text{cfg}_{i-1}$ 判定），则必须进行重配置（$r_{i,j}$ 由 $u_{i,j}$ 和“是否同构”共同决定），同时 $u_{i,j} \ge r_{i,j}$。
- **(9)**–**(13)** **(P2)** OCS 活动不重叠：
   - $t_{\text{prev\_e}_{i,j}}$ 记录 OCS $j$ 在步骤 $i$ 之前最近一次完成的活动时间（上一轮传输或重配置）；
   - 当前轮的重配置开始时间 $t_{\text{recfg\_s}_{i,j}}$ 不得早于该时间，从而避免同一 OCS 上活动的时间重叠。
- **(14)**–**(15)** 步骤完成与跨步同步（**P3**）：
   - 每步完成时间 $t_{\text{step\_e}_i}$ 至少为当步所有活跃 OCS 传输结束时间的最大值；
   - 下一步的任意传输开始时间不得早于上一步的完成时间。
- **(16)** CCT 定义：整体 CCT 是所有步骤完成时间的最大值，并由变量 $\text{CCT}$ 表示，是模型的优化目标。

---

### Implementation

Our current implementation uses the commercial solver **Gurobi** [@gurobi] to solve the MILP formulation, leveraging its advanced branch-and-cut algorithms to efficiently explore the $ \mathcal{O}(2^N) $ solution space.