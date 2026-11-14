# Benchmark results (2026-11-14T12:14:37, 12 cases x 1 repeats)

| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | Median ms | p95 ms | Cost / decision (USD, est.) |
|---|---|---|---|---|---|---|---|---|---|
| drex | drex-max-v1.1 | 75% | 50% | 100% | 0 | 0 | 316.04999999999995 | 400.9 | 2.842e-05 |
| rule-baseline | deterministic rules | 92% | 83% | 100% | 0 | 0 | 0.0 | 0.0 | 0.0 |

Cost is estimated from token counts and the per-1M-token prices set in .env. Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.

| Case | Expected | drex | rule-baseline |
|---|---|---|---|
| C01 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C02 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C03 | REQUEST_INFO | OK REQUEST_INFO | OK REQUEST_INFO |
| C04 | SPLIT:S1+S3 | OK SPLIT:S1+S3 | OK SPLIT:S1+S3 |
| C05 | BUY:S2 | OK BUY:S2 | OK BUY:S2 |
| C06 | REQUEST_INFO | OK REQUEST_INFO | X WAIT |
| C07 | EXPEDITE:PO-1001 | X REQUEST_INFO | OK EXPEDITE:PO-1001 |
| C08 | BUY:S1 | OK BUY:S1 | OK BUY:S1 |
| C09 | EXPEDITE:PO-1001 | X REQUEST_INFO | OK EXPEDITE:PO-1001 |
| C10 | ESCALATE | OK ESCALATE | OK ESCALATE |
| C11 | WAIT | OK WAIT | OK WAIT |
| C12 | ESCALATE | X BUY:S2 | OK ESCALATE |