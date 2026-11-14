# Benchmark results (2026-11-14T13:16:28, 18 cases x 1 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| drex | drex-max-v1.1 | 78% | 50% | 100% | 0 | 0 | 330.1 | 440.2 | 172.3 | 0.000029 |

## Outcomes on real held-out demand (fresh cases only)

Each chosen action is replayed against the actual M5 sales of the following 14 days, which the planner never saw. Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed. Total cost = spend + $30 per unmet case + $0.05 per case-day held (assumed, simulated).

| Provider | Fresh-case accuracy | Mean fill rate | Mean unmet cases | Mean total cost (USD) |
|---|---|---|---|---|
| drex | 83% | 95.0% | 19.0 | 1,856.97 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Hybrid = Drex first, comparison LLM only when Drex confidence < HYBRID_THRESHOLD (default 0.6); . Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | drex |
|---|---|---|
| C01 | BUY:S1 | OK BUY:S1 |
| C02 | BUY:S1 | OK BUY:S1 |
| C03 | REQUEST_INFO | OK REQUEST_INFO |
| C04 | SPLIT:S1+S3 | OK SPLIT:S1+S3 |
| C05 | BUY:S2 | OK BUY:S2 |
| C06 | REQUEST_INFO | OK REQUEST_INFO |
| C07 | EXPEDITE:PO-1001 | X REQUEST_INFO |
| C08 | BUY:S1 | OK BUY:S1 |
| C09 | EXPEDITE:PO-1001 | X REQUEST_INFO |
| C10 | ESCALATE | OK ESCALATE |
| C11 | WAIT | OK WAIT |
| C12 | ESCALATE | X BUY:S2 |
| C13 | BUY:S3 | OK BUY:S3 |
| C14 | BUY:S1 | X REQUEST_INFO |
| C15 | WAIT | OK WAIT |
| C16 | REQUEST_INFO | OK REQUEST_INFO |
| C17 | BUY:S1 | OK BUY:S1 |
| C18 | REQUEST_INFO | OK REQUEST_INFO |