> Note: this run contains only the ten blind cases N01-N10. The 'Held-out acc.' and 'Fresh-case accuracy' columns show 0% because no cases of those splits are in this run; read the 'Accuracy' column.

# Benchmark results (2026-11-14T14:27:41, 10 cases x 1 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| drex | drex-max-v1.1 | 80% | 0% | 100% | 0 | 0 | 414.9 | 582.2 | 165.4 | 0.000027 |
| rule-baseline | deterministic rules | 80% | 0% | 100% | 0 | 0 | 0.0 | 0.0 | - | 0.000000 |
| hybrid | drex-max-v1.1 | 90% | 0% | 100% | 0 | 0 | 347.5 | 3691.0 | 165.8 | 0.000896 |
| drex-evidence | drex-max-v1.1 | 100% | 0% | 100% | 0 | 0 | 337.9 | 487.3 | 150.9 | 0.000014 |
| llm | anthropic/claude-opus-5-5 | 100% | 0% | 100% | 0 | 0 | 2466.8 | 6534.0 | - | 0.007346 |

## Outcomes on real held-out demand (fresh cases only)

Each chosen action is replayed against the actual M5 sales of the following 14 days, which the planner never saw. Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed. Total cost = spend + $30 per unmet case + $0.05 per case-day held (assumed, simulated).

| Provider | Fresh-case accuracy | Mean fill rate | Mean unmet cases | Mean total cost (USD) |
|---|---|---|---|---|
| drex | 0% | 85.8% | 41.8 | 2,403.73 |
| rule-baseline | 0% | 94.1% | 17.4 | 2,435.73 |
| hybrid | 0% | 87.5% | 36.8 | 2,329.61 |
| drex-evidence | 0% | 94.1% | 17.4 | 2,435.73 |
| llm | 0% | 94.1% | 17.4 | 2,435.73 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Hybrid = Drex first, comparison LLM only when Drex confidence < HYBRID_THRESHOLD (default 0.6); hybrid escalated 10%. Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | drex | rule-baseline | hybrid | drex-evidence | llm |
|---|---|---|---|---|---|---|
| N01 | BUY:S4 | OK BUY:S4 | OK BUY:S4 | OK BUY:S4 | OK BUY:S4 | OK BUY:S4 |
| N02 | WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT |
| N03 | REQUEST_INFO | OK REQUEST_INFO | X WAIT | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| N04 | WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT |
| N05 | WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT | OK WAIT |
| N06 | EXPEDITE:PO-2001 | X REQUEST_INFO | OK EXPEDITE:PO-2001 | OK EXPEDITE:PO-2001 | OK EXPEDITE:PO-2001 | OK EXPEDITE:PO-2001 |
| N07 | BUY:S4 | X REQUEST_INFO | OK BUY:S4 | X REQUEST_INFO | OK BUY:S4 | OK BUY:S4 |
| N08 | BUY:S5 | OK BUY:S5 | OK BUY:S5 | OK BUY:S5 | OK BUY:S5 | OK BUY:S5 |
| N09 | REQUEST_INFO | OK REQUEST_INFO | X WAIT | OK REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| N10 | ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE | OK ESCALATE |