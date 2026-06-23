# AI Agent Autonomous Reproducibility Report

> **Date:** 2026-06-23
>
> This report documents a fully autonomous, zero-human-intervention reproduction
> of all paper results for the SWOT scheduler (overlap4ocs) using Claude Code as
> an AI agent. The agent acted as a simulated CoNEXT 2026 AE reviewer and
> completed the entire pipeline without any human intervention after the initial
> prompt.

## Motivation

Traditional Artifact Evaluation (AE) relies on human reviewers running documented
commands in a controlled environment. This report demonstrates a complementary
reproducibility pillar: an **AI agent autonomously re-executing the entire paper
pipeline from scratch**, with no human intervention after a single prompt.

The agent was given the same instructions a human AE reviewer would receive — the
artifact appendix, the reproducibility guide, and a reviewer role prompt — and
executed the full workflow independently: environment setup, smoke test, all 11
paper matrices, data preparation, and figure generation.

## Prompt

A single prompt was used (see [`prompt.txt`](prompt.txt) for the exact text).
The prompt instructs the agent to act as a simulated CoNEXT 2026 AE reviewer,
evaluate the artifact against ACM badging standards, and follow the AE appendix
and reproducibility guide. The prompt embeds "You have enough time to run all
data to check the producibility" and specifies unattended execution — no
confirmation or input after launch.

**Total human effort:** writing the prompt (~15 minutes) and reviewing the output.
**Human intervention after launch:** zero.

## Environment

| Item | Value |
|------|-------|
| Hardware | Intel Xeon Gold 6152 @ 2.10GHz (44 vCPUs) |
| RAM | 125 GB |
| OS | Ubuntu 20.04, Linux 5.15.0-139-generic, x86_64 |
| Python | 3.12.13 (via uv 0.11.18) |
| Solver | PuLP 3.3.0 → CBC 2.10.3 |
| Key deps | matplotlib 3.10.1, networkx 3.4.2, numpy 2.3.5, pandas 2.3.3 |

## Execution Summary

The agent cloned the repository into a clean directory, set up the environment
via `uv sync --extra notebook --python 3.12`, ran a smoke test, then executed
the full matrix pipeline — all 11 paper matrices sequentially, data preparation,
and figure generation.

| Metric | Value |
|--------|-------|
| Total matrix experiments | 11 (all paper matrices) |
| Total individual runs | 298 |
| Successful runs | 295 (99.0%) |
| Failed runs | 3 (all `a2a_pairwise` at p=256 — PuLP/CBC scalability limit) |
| Total wall-clock time | ~6.5 hours |
| Merged CSV rows generated | 208 rows across 4 prepared CSVs |
| Paper figures regenerated | 12 PDF figures |

## Key Quantitative Results

The key trends match the paper within expected MILP solver variance:

| Paper Figure | Paper Trend | Observed Trend | Status |
|---|---|---|---|
| Fig. 7(a): ReduceScatter CCT vs msg size | Up to 84.0% vs one-shot | 0.0%–84.0% vs one-shot | **Reproduced** (exact match) |
| Fig. 7(b): AllReduce CCT vs msg size | Up to 83.7% vs one-shot | 0.0%–83.7% vs one-shot | **Reproduced** (exact match) |
| Fig. 7(c): A2A Bruck | Up to 89.7% vs one-shot | 0.0%–87.0% vs one-shot | **Reproduced** (2.7pp gap: CBC solver variance) |
| Fig. 7(d): A2A Pairwise | Up to 83.8% vs one-shot | 0.0%–83.8% vs one-shot | **Reproduced** (exact match) |
| Fig. 8(a): AllReduce scalability | Improves with cluster size | Confirmed across p=4−1024 | **Reproduced** |
| Fig. 8(b): A2A Pairwise scalability | Similar scalability trend | Confirmed across p=5−14 | **Reproduced** |
| Fig. 9(a): A2A primitive envelope | Best-of-breed envelope | Regenerated successfully | **Reproduced** |
| Fig. 9(b): AR primitive envelope | Near-optimal baselines | Regenerated successfully | **Reproduced** |
| Fig. 10: Impact of k | Diminishing returns | Regenerated k=2,4,8 | **Reproduced** |
| Fig. 11: Impact of T_reconf | Overlap effectiveness | Regenerated 0.2−20ms | **Reproduced** |

**Solver variance note:** The A2A Bruck max improvement differs by 2.7 percentage
points from the paper's value (87.0% vs 89.7%). This is within the expected range
for CBC branch-and-bound with a 120-second time limit on different hardware, as
documented in `docs/reproducibility.md`. All other key metrics match exactly.

## Issues Encountered

- **3/298 runs failed:** All were `a2a_pairwise` at p=256 with PuLP/CBC — model
  building hangs for this algorithm/scale combination on the open-source solver
  stack. These runs are at the extreme end of the parameter space and do not
  affect any paper figure or claim.
- **Git clone via HTTPS** was unreliable from the evaluation environment; the
  repository was obtained via ZIP download of the main branch (functionally
  equivalent).

## Evidence Archives

The following assets are included in the GitHub release:

| Asset | Description |
|-------|-------------|
| `ai-agent-repro-output.tar.gz` | All regenerated outputs: 11 matrix CSVs, 4 merged CSVs, 12 paper figure PDFs, progress JSONs, review draft |
| `ai-agent-repro-conversation.tar.gz` | Exported Claude Code session transcript (prompt + agent responses + tool calls, 1484 lines) |
| `ai-agent-repro-manifest.json` | SHA256 checksums and file listing for above archives |

## Conclusion

This reproduction demonstrates two key points:

1. **AE is a means, not the end.** This artifact received "Artifact Available"
   and "Artifact Evaluated - Functional" badges (not Results Reproduced), yet
   the paper results are genuinely reproducible, as shown by both human AE
   reviewers and this AI agent audit.

2. **AI agent autonomous reproduction is a viable reproducibility pillar.**
   A single prompt to Claude Code was sufficient to reproduce all 12 paper
   figures without human intervention — complementing traditional AE with an
   independent, fully automated verification path that any reader can replicate.
