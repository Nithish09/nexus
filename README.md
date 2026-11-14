# Nexus — supply-chain purchasing decisions with Drex

**Drexathon 2026 · Track: Apex Predator (Drex vs. the Giants)**

Nexus answers: *given what we know today, what should we order, from which supplier, in what quantity, and when — while controlling cost, shortage risk and expiry waste?*

A frontier LLM is often used as the "decision step" in planning agents. Nexus hands that step to **Drex** (a decision model that returns a probability for every allowed action) and measures accuracy, latency and cost against a comparison LLM on identical cases.

> **Demand is historical (M5 / Walmart daily sales) once you run `python scripts/fetch_m5.py`; all supplier terms, inventory, prices and orders are simulated.** Product names are illustrative labels for anonymized M5 items. No real supplier transaction is ever placed.

## How it works

```
Supplier docs ──NDI──► Document & Data Agent ──► facts {source, excerpt, status, learned_day}
                                                   │
Seeded scenario ──► Demand & Inventory Agent ──────┤  seasonal-naive forecast, projection,
                    (reservations + quality holds   │  net need (incl. near-term gaps)
                     are never "available")         ▼
                    Supplier Assessment + Procurement Planning
                    candidate actions: BUY:Sx | SPLIT | EXPEDITE | WAIT | REQUEST_INFO | ESCALATE
                    (quantities rounded to MOQ / pack; cost, unmet demand, expiry waste computed)
                                                   │
                    Deterministic validator ───────┤  quote validity, MOQ, pack, capacity, shelf life,
                    (hard-invalid options removed)  │  storage, budget, approved supplier, duplicates
                                                   ▼
                    Drex decision (System 1)  — choice over allowed action IDs + reason code
                                                   │
                    Verification & Approval ───────┤  model output can never override validation;
                                                   ▼  purchases need human approval
                    Simulated ERP ledger (SQLite, idempotent action keys)
```

The model never invents quantities: it chooses among action IDs that Nexus computed and checked. Explanations are built from validated facts and the chosen reason code; no chain-of-thought is requested or shown.

### Where each tool is used

| Tool | Use in Nexus | Status |
|---|---|---|
| **Drex** | Every procurement decision (`nexus/decide.py::DrexProvider`): one `choice` question over candidate action IDs + one `choice` question for the reason code. Probabilities are shown in the UI. | Live when `NACE_API_KEY` is set: `POST https://console.nace.ai/v1/systemone`, model `drex-max-v1.1` |
| **NDI** | Supplier quotes, emails and delay notices: NDI Extract with a JSON Schema and citations via `nace-sdk` (`nexus/documents.py::ndi_extract`), cached by content hash. | Live when `NACE_API_KEY` is set; on any NDI error the UI shows the error and uses a clearly labeled local regex extractor |
| **DeepInfra** | Hosts the comparison System 2 LLM for the benchmark (`LLMProvider`). | Live when `SYSTEM2_MODEL` set |
| **Intern** | Coding agent for one script, `scripts/threshold_sweep.py` (see "Intern usage"). | Used once, headlessly; not part of the running product |

## Run it

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_m5.py   # historical M5 demand (~50 MB download); skip = seeded synthetic demand
cp .env.example .env      # add keys; leave empty for offline demo mode
pytest -q                 # correctness tests (never call live APIs)
python benchmark.py       # runs every configured provider; unconfigured ones are skipped, never faked
streamlit run app.py
```

**Demo flow:** sidebar → *1. Run weekly plan* (oat milk is covered by open order PO-1001; cold brew needs an order) → *2. Supplier delay notice arrives* → NDI reads DOC-D1: the new **ship** date is Nov 24 + 3 days transit, so **arrival** moves from day 5 to day 11 → replan → Drex chooses between expediting, a bridge order or a tentative fast supplier, and the validator checks it → approve (simulated ERP, duplicate-proof).

**Modes:** with no keys the app runs in **offline demo mode** using the deterministic rule baseline, labeled as such. Offline mode never produces results presented as model benchmarks.

## Benchmark

`python benchmark.py` runs 18 cases (`nexus/cases.py`) through Drex, the comparison LLM and a rule baseline with the same candidates, the same allowed actions and the same validator. Each case's expected action is written down with its reasoning, independent of any model output. Six cases are `dev` and six `heldout`. The `heldout` results were seen once before an option-wording fix for EXPEDITE (which did not change any answer), so six more `fresh` cases (C13-C18) were added afterwards and never used for tuning. The hybrid threshold (0.6) was also chosen after seeing the first Drex run.

**Outcome scoring on real demand.** The `fresh` cases plan on M5 history that ends 14 days before the end of the data. Each chosen action is then replayed against the actual sales of those 14 days (never shown to the planner or the model) to get fill rate, unmet cases and total cost (spend + an assumed $30 per unmet case + $0.05 per case-day held). Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed.

**Hybrid provider.** Drex decides; when its confidence is below `HYBRID_THRESHOLD` the same question goes to the System 2 LLM. The benchmark reports the escalation rate.

| Case | Trap |
|---|---|
| C01 | normal order; fast supplier's capacity unverified |
| C02 | lowest unit price, but MOQ causes expiry waste |
| C03 | only the fast supplier avoids a stockout, but its capacity is tentative |
| C04 | split sourcing required (capacity + expired quote) |
| C05 | expired quote |
| C06 | conflicting delivery updates |
| C07 | ship date mistaken for arrival date |
| C08 | inventory on quality hold |
| C09 | supplier delay after the order was placed |
| C10 | insufficient budget |
| C11 | duplicate daily run |
| C12 | no feasible plan |
| C13 | cheapest bulk order exceeds warehouse storage |
| C14 | cheaper supplier is unconfirmed; verified one covers demand |
| C15 | delayed order that still arrives in time (no expedite fee needed) |
| C16 | supply sufficient only if a tentatively reported slip does not happen |
| C17 | expediting is not enough; bridge order needed |
| C18 | verified option mostly expires, alternative unconfirmed |

Metrics: accuracy (all / held-out), valid-output rate, validator rejections, errors, median and p95 decision latency, estimated cost per decision (token counts × prices you set in `.env`). Results are written to `results/benchmark.md` and `results/benchmark.json`.

### Results (final run: 2026-11-14 13:20 PT, 18 cases x 1 repeat, `results/benchmark_final_vs_opus55.md`)

| Provider | Model | Accuracy (18) | Fresh cases (6) | Median latency | p95 latency | Est. cost / decision |
|---|---|---|---|---|---|---|
| Drex alone | `drex-max-v1.1` | 14/18 (78%) | 5/6 | 354 ms (184 ms model time) | 465 ms | $0.000029 |
| **Hybrid** (Drex, LLM if confidence < 0.6) | `drex-max-v1.1` -> `anthropic/claude-opus-5-5` | **17/18 (94%)** | 6/6 | 406 ms | 3,988 ms | $0.0021 |
| LLM alone | `anthropic/claude-opus-5-5` (via DeepInfra) | 17/18 (94%) | 6/6 | 3,001 ms | 3,686 ms | $0.0079 |
| Rule baseline | deterministic rules | 15/18 (83%) | 4/6 | ~0 ms | ~0 ms | $0 |

What this run shows:

* **Drex alone vs Opus 5.5:** about 8.5x faster at the median (354 ms vs 3,001 ms round trip) and about 270x cheaper per decision, but less accurate (78% vs 94%). Every Drex output was a valid action ID and nothing it chose violated a hard constraint.
* **Hybrid matched Opus 5.5's accuracy (17/18) while calling Opus on only 4 of 18 decisions (22%)**: about 3.8x cheaper than Opus alone and about 7x faster at the median. Its p95 latency is the same as the LLM's, because escalated decisions still wait for the LLM.
* **Drex's confidence was informative:** 3 of its 4 misses (C07, C09, C14) had confidence below 0.6 and were corrected by escalation. The one confident miss, C12 (buy from S2 to reduce an unavoidable shortage instead of escalating), is the same answer Opus gave; the expected label there is debatable.
* **Models beat the rules where evidence matters:** the rule baseline misses C06, C15 and C16 (conflicting or tentative evidence, an unnecessary expedite); Drex alone gets all three.
* **Outcomes on real held-out demand (fresh cases):** hybrid and Opus both reach a 97.5% mean fill rate at a mean total cost of $2,108; Drex alone 95.0% / $1,857 (its cautious REQUEST_INFO on C14 counts as "no order today"); rules 97.5% / $2,368 (they pay an unnecessary expedite fee in C15).

Caveats, stated plainly:

* 18 cases, one repeat. In an earlier 3-repeat run on the first 12 cases Drex gave identical answers every time, but this is still a small sample.
* The 0.6 hybrid threshold was chosen after seeing Drex's first run on C01-C12, and two decisions sit right at it (C03 at 0.596, C16 at 0.603), so the 22% escalation rate is sensitive to that choice. The six fresh cases were never used for tuning; on those the hybrid scored 6/6 with one escalation (C14).
* Costs are estimates: token counts x list prices ($0.04 per 1M input tokens for Drex as set in `.env`; $4 / $20 per 1M input / output tokens for Opus 5.5 on DeepInfra). Latency is round trip from a phone hotspot and includes network time.
* The comparison prompt for the LLM asks for a JSON answer only (no reasoning text); a different prompt could change its latency and cost.

Run history kept in `results/`: `benchmark_run1_*` and `run2_*` (Drex on C01-C12, before and after an EXPEDITE wording fix that changed no answers), `run3_*` (Opus 5.5 valid; every Drex call returned HTTP 403 because the venue Wi-Fi was rate-limited by the API host, so its Drex and hybrid rows are invalid), `run4_*` (Drex on all 18 cases), and the final run above. Only results produced by an actual run are committed.

Honest limitations: 18 cases is a small sample; the planning dates are simulated (2016 sales history is replayed as recent demand); the rule baseline is strong here because candidate generation does most of the arithmetic — the decision layer matters most in evidence cases (conflicts, tentative commitments). The comparison model is named by its exact ID in every table.

## Data provenance

* **Demand: historical.** M5 Forecasting - Accuracy (Walmart daily unit sales; Makridakis, Spiliotis & Assimakopoulos), downloaded by `scripts/fetch_m5.py` from the public Nixtla mirror. Nexus uses items `FOODS_3_090`, `FOODS_3_288` and `FOODS_3_586`, summed over the 4 California stores (treated as one DC's demand), last 28 days of the dataset (2016-04-25 to 2016-05-22), converted to cases at an **assumed** pack size (6, 6 and 8 units). The raw data is not committed (`data/history/` is git-ignored). M5 items are anonymized, so the product names ("Oat milk", "Cold brew") are illustrative labels, and M5 contains no supplier, cost, capacity, inventory or expiry data. Observed sales can understate demand on stockout days.
* If the M5 subset is absent, demand falls back to a seeded synthetic series and the UI says so. The benchmark expectations were checked under both.
* Suppliers, quotes, inventory, open orders, budgets, documents in `data/docs/`: **simulated**.

## Intern usage

* **Version:** `intern-agent` 0.30.1 (installed from `github.com/nace-ai/intern` at commit `e4e32d5`), run headlessly with `--system1 drex-latest --system2 deepinfra/Qwen/Qwen3.8-27B`.
* **What Intern wrote:** `scripts/threshold_sweep.py`, from a single prompt describing the analysis (see the commit "Add hybrid threshold sweep"). It reads the final benchmark results and recomputes the hybrid's escalation rate and accuracy at different confidence thresholds, with no API calls.
* **What Intern did not write:** the rest of the code base, tests, README and slides were written with another AI coding assistant (Claude) and reviewed by the team. Intern is not used inside the running product.

Output of `python scripts/threshold_sweep.py` on the final run:

| Threshold | Escalation rate | Hybrid accuracy |
|---|---|---|
| 0.4 | 0% | 78% |
| 0.5 | 6% | 83% |
| 0.6 | 22% | 94% |
| 0.7 | 39% | 94% |
| 0.8 | 44% | 94% |
| 0.9 | 61% | 94% |

On these 18 cases, 0.6 is the lowest threshold that reaches the LLM's accuracy; raising it further only sends more decisions to the LLM without changing accuracy. This is an in-sample analysis of one run, not a tuned or validated setting.

## Future work

Multi-location transfers, acknowledged → shipped → received → inspected tracking with receipt-driven inventory updates, multi-period optimisation (OR-Tools), production scheduling (BOM, yield, capacity fields), more M5 items and stores, scenario-based lead-time uncertainty.

## Repository layout

```
app.py                 Streamlit dashboard
benchmark.py           Drex vs LLM vs rule baseline
nexus/config.py        env-based settings (no secrets in code)
nexus/scenario.py      scenario: historical demand + simulated supplier terms
nexus/history.py       M5 demand loader
scripts/fetch_m5.py    downloads M5 and extracts the 3-item subset
scripts/threshold_sweep.py  hybrid threshold analysis (written with Intern)
nexus/planning.py      forecast, projection, candidates, validator
nexus/documents.py     NDI adapter + labeled local fallback, delay-notice events
nexus/decide.py        Drex / LLM / rule providers (one interface)
nexus/planner.py       planning run, verification, idempotent ledger
nexus/cases.py         18 benchmark cases with expected actions
data/docs/             simulated supplier documents
tests/test_core.py     correctness tests
```
