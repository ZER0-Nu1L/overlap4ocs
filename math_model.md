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

- **(1)** **Total data volume constraint**: For each step $i$, the sum of data volumes transmitted across all OCSes equals $m_i$.
- **(2)** **Bandwidth + latency constraint**: Transmission duration equals "data volume divided by bandwidth $B$" plus fixed end-to-end latency $T_{\text{lat}}$ (effective when $u_{i,j}=1$).
- **(3)** **Usage indicator constraint**: Only when $u_{i,j}=1$ can $d_{i,j}$ be positive; otherwise constrained to 0 by big-$M$ method.
- **(4)** **Reconfiguration duration**: If and only if $r_{i,j}=1$, reconfiguration lasts $T_{\text{recfg}}$ time.
- **(5)** **(P1) Reconfiguration precedes transmission**: Transmission start time must not be earlier than reconfiguration end time.
- **(6)**–**(8)** **Configuration change and usage logic**:
   - First step defaults to requiring reconfiguration ($r_{1,j} \ge u_{1,j}$).
   - In subsequent steps, if the current topology differs from the previous step and the OCS is used (determined by code comparing $\text{cfg}_i$ vs $\text{cfg}_{i-1}$), reconfiguration is required ($r_{i,j}$ determined by $u_{i,j}$ and "whether configurations match"), while maintaining $u_{i,j} \ge r_{i,j}$.
- **(9)**–**(13)** **(P2) No overlapping OCS activities**:
   - $t_{\text{prev\_e}_{i,j}}$ records the last completion time of previous activities (transmission or reconfiguration) on OCS $j$ before step $i$;
   - Current round's reconfiguration start time $t_{\text{recfg\_s}_{i,j}}$ must not be earlier than this time, preventing temporal overlap of activities on the same OCS.
- **(14)**–**(15)** **Step completion and cross-step synchronization (P3)**:
   - Each step's completion time $t_{\text{step\_e}_i}$ is at least the maximum of all active OCS transmission end times in that step;
   - Any transmission start time in the next step must not be earlier than the previous step's completion time.
- **(16)** **CCT definition**: Overall CCT is the maximum of all step completion times, represented by variable $\text{CCT}$, which is the optimization objective.

---

### Implementation

Our current implementation uses the commercial solver **Gurobi** [@gurobi] to solve the MILP formulation, leveraging its advanced branch-and-cut algorithms to efficiently explore the $ \mathcal{O}(2^N) $ solution space.