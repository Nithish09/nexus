# Benchmark results (2026-11-14T12:20:15, 12 cases x 3 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| rule-baseline | deterministic rules | 92% | 83% | 100% | 0 | 0 | 0.0 | 0.0 | - | 0.000000 |
| drex | drex-max-v1.1 | 75% | 50% | 100% | 0 | 0 | 301.6 | 447.0 | 134.9 | 0.000029 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | rule-baseline | drex |
|---|---|---|---|
| C01 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C02 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C03 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| C04 | SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 |
| C05 | BUY:S2 | OK BUY:S2 | OK BUY:S2 |
| C06 | REQUEST_INFO | X WAIT | OK REQUEST_INFO |
| C07 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X REQUEST_INFO |
| C08 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C09 | EXPEDITE:PO-1001 | OK EXPEDITE:PO-1001 | X REQUEST_INFO |
| C10 | ESCALATE | OK ESCALATE | OK ESCALATE |
| C11 | WAIT | OK WAIT | OK WAIT |
| C12 | ESCALATE | OK ESCALATE | X BUY:S2 |