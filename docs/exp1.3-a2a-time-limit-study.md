# Exp1.3 A2A Time-Limit Study

Date: 2026-03-07

## What Was Changed

- Ran full `a2a_pairwise` sweeps for `solver_time_limit in {200, 600, 900, 1200, 1500, 3000}` at `p=256, k=8, B=12.5`.
- Built two plotting views:
  - Pairwise-only (no one-shot available in pairwise CSVs).
  - Mixed view (pairwise + historical `a2a_bruck@120`, includes one-shot).

## Figure Outputs

- Pairwise-only (supports point 1): `figures/paper_debug/pair_only/exp1.3_a2a_256_pair_t*.pdf`
- Mixed with one-shot (supports point 2): `figures/paper_debug/with_oneshot/exp1.3_a2a_256_mix_t*.pdf`
- Both sets use `zoom_range=(0,8)`, `gain_range=(0,13)`.

## Quantitative Summary

Raw summary table: [`docs/exp1.3-a2a-time-limit-summary.csv`](./exp1.3-a2a-time-limit-summary.csv)

### A) Pairwise-only (vs Strawman-ICR)

| time_limit | mean improvement (%) | median improvement (%) | m=0.25 gap vs t3000 (%) | m=0.5 gap vs t3000 (%) |
|---|---:|---:|---:|---:|
| 200 | 4.02 | 0.89 | +154.04 | +124.56 |
| 600 | 43.19 | 52.98 | +154.04 | +124.56 |
| 900 | 53.61 | 59.02 | -3.39 | -1.77 |
| 1200 | 53.43 | 56.80 | +1.01 | +8.25 |
| 1500 | 54.08 | 58.08 | -2.27 | -11.07 |
| 3000 | 46.41 | 55.79 | 0.00 | 0.00 |

Interpretation: increasing `solver_time_limit` clearly improves pairwise quality from low limits (`200/600`) to high limits (`900+`), though CBC time-limited search is not strictly monotonic point-by-point.

### B) Mixed View (Pairwise + Bruck@120, with one-shot)

| time_limit | pairwise selected | bruck selected | mean gain vs best-known (%) |
|---|---:|---:|---:|
| 200 | 0 | 13 | 19.82 |
| 600 | 0 | 13 | 19.82 |
| 900 | 0 | 13 | 19.82 |
| 1200 | 0 | 13 | 19.82 |
| 1500 | 0 | 13 | 19.82 |
| 3000 | 0 | 13 | 19.82 |

Interpretation: for primitive-level comparison, `SWOT + a2a_bruck` dominates all message sizes; pairwise time-limit tuning does not change the final best-curve trend.

## Solver-Trace Observations

- `t=600`: `m=0.25` and `m=0.5` never entered the good region (`CCT <= 30 ms`) before timeout.
- `t=900`: both hard points entered `<=25 ms` late (`~843s` for `m=0.25`, `~818s` for `m=0.5`).
- `t=1200`: `m=0.5` entered `<=30 ms` (`~958s`) but did not reach `<=25 ms` within limit.
- `t=1500`: both hard points entered `<=25 ms` earlier (`~797s`, `~740s`) and continued improving to final incumbent.

## Final Takeaways

1. Pairwise-only view confirms that higher time limits can substantially increase SWOT gain over Strawman-ICR.
2. Mixed primitive-level view confirms those gains are dominated by `SWOT + a2a_bruck`; this is the more decision-relevant comparison.
3. Setting `exp1.3-a2a_bruck` time limit to `120` keeps consistency and does not change the final trend conclusions.
