# Corrected Figure 11 data

`results.csv` contains the 84 saved trials used for the replacement Figure 11: three algorithms, four reconfiguration delays, and seven message sizes. Its SHA-256 is recorded in `provenance.json`.

The corrected ordinate is `100 * (optimized_cct - ideal_cct) / optimized_cct`. The published plotting path instead used `baseline_cct`, which describes Strawman-ICR rather than SWOT. CCT columns are in milliseconds and exclude one initial preconfiguration interval; `message_mib` is a legacy column name whose numerical values are decimal MB. A plane bandwidth of 25 means 25 GB/s = 200 Gbps.

`run_id` and `metrics_path` preserve the original trial identifiers for traceability; the historical machine's log directories are not required to redraw the figure. New runs create their own evidence using `scripts/run_fig11_matrix.py`. Solver status, fallback and bounds are retained in the table. A configured target gap does not certify time-limited results as optimal.

See [reproduction instructions](../../docs/fig11-correction.md).
