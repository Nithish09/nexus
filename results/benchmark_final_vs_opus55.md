# Benchmark results (2026-11-14T13:20:41, 18 cases x 1 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| rule-baseline | deterministic rules | 83% | 83% | 100% | 0 | 0 | 0.0 | 0.0 | - | 0.000000 |
| drex | drex-max-v1.1 | 78% | 50% | 100% | 0 | 0 | 354.1 | 465.1 | 184.4 | 0.000029 |
| hybrid | drex-max-v1.1 | 94% | 83% | 100% | 0 | 0 | 406.0 | 3987.8 | 205.6 | 0.002069 |
| llm | anthropic/claude-opus-5-5 | 94% | 83% | 100% | 0 | 0 | 3001.1 | 3686.4 | - | 0.007899 |

## Outcomes on real held-out demand (fresh cases only)

Each chosen action is replayed against the actual M5 sales of the following 14 days, which the planner never saw. Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed. Total cost = spend + $30 per unmet case + $0.05 per case-day held (assumed, simulated).

| Provider | Fresh-case accuracy | Mean fill rate | Mean unmet cases | Mean total cost (USD) |
|---|---|---|---|---|
| rule-baseline | 67% | 97.5% | 4.7 | 2,368.09 |
| drex | 83% | 95.0% | 19.0 | 1,856.97 |
| hybrid | 100% | 97.5% | 4.7 | 2,108.09 |
| llm | 100% | 97.5% | 4.7 | 2,108.09 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Hybrid = Drex first, comparison LLM only when Drex confidence < HYBRID_THRESHOLD (default 0.6); hybrid escalated 22%. Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | rule-baseline | drex | hybrid | llm |
|---|---|---|---|---|---|
| C01 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C02 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C03 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| C04 | SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 |
| C05 | BUY:S2 | OK BUY:S2 | OK BUY:S2 | OK BUY:S2 | OK BUY:S2 |
| C06 | REQUEST_INFO | X WAIT | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| C07 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X REQUEST_INFO | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 |
| C08 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C09 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X REQUEST_INFO | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 |
| C10 | ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE |
| C11 | WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT |
| C12 | ESCALATE | OK ESCALATE | X BUY:S2 | X BUY:S2 | X BUY:S2 |
| C13 | BUY:S3 | OK BUY:S3 | OK BUY:S3 | OK BUY:S3 | OK BUY:S3 |
| C14 | BUY:S1 | OK BUY:S1 | X REQUEST_INFO | OK BUY:S1 | OK BUY:S1 |
| C15 | WAIT | X EXPEDITE:PO-1001 | OK WAIT | OK WAIT | OK WAIT |
| C16 | REQUEST_INFO | X WAIT | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| C17 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C18 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |