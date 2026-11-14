# Benchmark results (2026-11-14T12:59:44, 18 cases x 3 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| llm | anthropic/claude-opus-5-5 | 96% | 89% | 100% | 0 | 0 | 2764.2 | 5422.4 | - | 0.008233 |
| hybrid | drex-max-v1.1 -> anthropic/claude-opus-5-5 | 94% | 83% | 100% | 0 | 0 | 2757.9 | 4845.9 | - | 0.008168 |
| rule-baseline | deterministic rules | 83% | 83% | 100% | 0 | 0 | 0.0 | 0.0 | - | 0.000000 |
| drex | drex-max-v1.1 | 11% | 17% | 0% | 54 | 54 | - | - | - | 0.000025 |

## Outcomes on real held-out demand (fresh cases only)

Each chosen action is replayed against the actual M5 sales of the following 14 days, which the planner never saw. Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed. Total cost = spend + $30 per unmet case + $0.05 per case-day held (assumed, simulated).

| Provider | Fresh-case accuracy | Mean fill rate | Mean unmet cases | Mean total cost (USD) |
|---|---|---|---|---|
| llm | 100% | 97.5% | 4.7 | 2,108.09 |
| hybrid | 100% | 97.5% | 4.7 | 2,108.09 |
| rule-baseline | 67% | 97.5% | 4.7 | 2,368.09 |
| drex | 0% | 89.8% | 48.2 | 1,619.72 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Hybrid = Drex first, comparison LLM only when Drex confidence < HYBRID_THRESHOLD (default 0.6); hybrid escalated 100%. Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | llm | hybrid | rule-baseline | drex |
|---|---|---|---|---|---|
| C01 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | X ESCALATE |
| C02 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | X ESCALATE |
| C03 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | X ESCALATE |
| C04 | SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 | X ESCALATE |
| C05 | BUY:S2 | OK BUY:S2 | OK BUY:S2 | OK BUY:S2 | X ESCALATE |
| C06 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | X WAIT | X ESCALATE |
| C07 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X ESCALATE |
| C08 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | X ESCALATE |
| C09 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X ESCALATE |
| C10 | ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE |
| C11 | WAIT | OK WAIT | OK WAIT | OK WAIT | X ESCALATE |
| C12 | ESCALATE | X BUY:S2 | X BUY:S2 | OK ESCALATE | OK ESCALATE |
| C13 | BUY:S3 | OK BUY:S3 | OK BUY:S3 | OK BUY:S3 | X ESCALATE |
| C14 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | X ESCALATE |
| C15 | WAIT | OK WAIT | OK WAIT | X EXPEDITE:PO-1001 | X ESCALATE |
| C16 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | X WAIT | X ESCALATE |
| C17 | BUY:S1 | OK BUY:S1 | OK BUY:S1 | OK BUY:S1 | X ESCALATE |
| C18 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO | X ESCALATE |