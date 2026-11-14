"""Drex vs comparison LLM vs rule baseline on identical cases.

Usage:
  python benchmark.py                      # runs every provider that is configured
  python benchmark.py --providers drex llm --repeats 3

Same cases, same candidate generation, same allowed action IDs, same deterministic validation
for every provider. Offline (unconfigured) providers are skipped, never simulated.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from nexus.cases import CASES
from nexus.decide import get_provider
from nexus.planner import plan_product

OUT = Path(__file__).parent / "results"


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def _outcomes(rs: list[dict]) -> dict:
    o = [r["outcome"] for r in rs if r.get("outcome")]
    if not o:
        return {"outcome_n": 0}
    return {"outcome_n": len(o), "fill_rate_mean": round(sum(x["fill_rate"] for x in o) / len(o), 4),
            "unmet_cases_mean": round(sum(x["unmet_cases"] for x in o) / len(o), 1),
            "total_cost_usd_mean": round(sum(x["total_cost_usd"] for x in o) / len(o), 2)}


def run(providers: list[str], repeats: int = 1) -> dict:
    rows, summary = [], {}
    for name in providers:
        prov = get_provider(name)
        if name != "rule-baseline" and not prov.live:
            summary[name] = {"skipped": "not configured (no API key / model) - no results fabricated"}
            continue
        for _ in range(repeats):
            for cid, build, expected, split, why in CASES:
                scn = build()
                plan = plan_product(scn, scn.products[0], prov)
                d = plan.decision
                rows.append({
                    "provider": name, "model": d.model, "case": cid, "split": split, "expected": expected,
                    "model_action": d.action, "final_action": plan.final_action, "reason": d.reason,
                    "correct": plan.final_action == expected, "valid_output": d.valid_output,
                    "rejected_by_validator": plan.final_action != d.action,
                    "latency_ms": round(d.latency_ms, 1), "model_ms": d.model_ms, "input_tokens": d.input_tokens,
                    "output_tokens": d.output_tokens, "cost_usd": d.cost_usd, "error": d.error,
                    "outcome": plan.outcome,
                    "confidence": d.confidence, "escalated": d.escalated, "drex_confidence": d.drex_confidence,
                })
    for name in {r["provider"] for r in rows}:
        rs = [r for r in rows if r["provider"] == name]
        lat = [r["latency_ms"] for r in rs if r["error"] is None]
        summary[name] = {
            "model": rs[0]["model"], "n": len(rs),
            "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
            "accuracy_heldout": round(sum(r["correct"] for r in rs if r["split"] == "heldout")
                                      / max(1, sum(r["split"] == "heldout" for r in rs)), 3),
            "accuracy_fresh": round(sum(r["correct"] for r in rs if r["split"] == "fresh")
                                    / max(1, sum(r["split"] == "fresh" for r in rs)), 3),
            **_outcomes(rs),
            "valid_output_rate": round(sum(r["valid_output"] for r in rs) / len(rs), 3),
            "validator_rejections": sum(r["rejected_by_validator"] for r in rs),
            "errors": sum(r["error"] is not None for r in rs),
            "escalation_rate": round(sum(bool(r.get("escalated")) for r in rs) / len(rs), 3),
            "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
            "latency_ms_p95": pct(lat, 0.95),
            "model_ms_median": (lambda m: round(statistics.median(m), 1) if m else None)(
                [r["model_ms"] for r in rs if r.get("model_ms") is not None]),
            "cost_usd_per_decision": round(sum(r["cost_usd"] for r in rs) / len(rs), 8),
        }
    return {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "repeats": repeats,
            "n_cases": len(CASES), "summary": summary, "rows": rows}


def to_markdown(res: dict) -> str:
    lines = [f"# Benchmark results ({res['run_at']}, {res['n_cases']} cases x {res['repeats']} repeats)", "",
             "| Provider | Model | Accuracy | Held-out acc. | Valid output | Validator rejections | Errors | "
             "Median ms (round trip) | p95 ms | Median model ms | Cost / decision (USD, est.) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in res["summary"].items():
        if "skipped" in s:
            lines.append(f"| {name} | - | skipped: {s['skipped']} | | | | | | | | |")
            continue
        lines.append(f"| {name} | {s['model']} | {s['accuracy']:.0%} | {s['accuracy_heldout']:.0%} | "
                     f"{s['valid_output_rate']:.0%} | {s['validator_rejections']} | {s['errors']} | "
                     f"{s['latency_ms_median'] if s['latency_ms_median'] is not None else '-'} | "
                     f"{s['latency_ms_p95'] if s['latency_ms_p95'] is not None else '-'} | "
                     f"{s.get('model_ms_median') if s.get('model_ms_median') is not None else '-'} | "
                     f"{s['cost_usd_per_decision']:.6f} |")
    lines += ["", "## Outcomes on real held-out demand (fresh cases only)", "",
              "Each chosen action is replayed against the actual M5 sales of the following 14 days, which the planner "
              "never saw. Only today's action is simulated, so REQUEST_INFO / ESCALATE count as no order placed. "
              "Total cost = spend + $30 per unmet case + $0.05 per case-day held (assumed, simulated).", "",
              "| Provider | Fresh-case accuracy | Mean fill rate | Mean unmet cases | Mean total cost (USD) |",
              "|---|---|---|---|---|"]
    for name, s in res["summary"].items():
        if "skipped" not in s and s.get("outcome_n"):
            lines.append(f"| {name} | {s['accuracy_fresh']:.0%} | {s['fill_rate_mean']:.1%} | "
                         f"{s['unmet_cases_mean']} | {s['total_cost_usd_mean']:,.2f} |")
    lines += ["", "Cost is estimated from token counts and the per-1M-token prices set in .env. "
              "Hybrid = Drex first, comparison LLM only when Drex confidence < HYBRID_THRESHOLD (default 0.6); "
              + "; ".join(f"{n} escalated {s['escalation_rate']:.0%}" for n, s in res["summary"].items()
                          if s.get("escalation_rate")) + ". "
              "Rule baseline latency is local CPU time. Demand is historical M5 when fetched; supplier terms and inventory are simulated.", "",
              "| Case | Expected | " + " | ".join(p for p in res['summary'] if 'skipped' not in res['summary'][p]) + " |",
              "|---|---|" + "---|" * sum('skipped' not in s for s in res['summary'].values())]
    provs = [p for p in res["summary"] if "skipped" not in res["summary"][p]]
    for cid, _, exp, _, _ in CASES:
        cells = []
        for p in provs:
            r = next((r for r in res["rows"] if r["provider"] == p and r["case"] == cid), None)
            cells.append(("OK " if r and r["correct"] else "X ") + (r["final_action"] if r else "-"))
        lines.append(f"| {cid} | {exp} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", nargs="+", default=["drex", "llm", "hybrid", "rule-baseline"])
    ap.add_argument("--repeats", type=int, default=1)
    a = ap.parse_args()
    res = run(a.providers, a.repeats)
    OUT.mkdir(exist_ok=True)
    (OUT / "benchmark.json").write_text(json.dumps(res, indent=2))
    md = to_markdown(res)
    (OUT / "benchmark.md").write_text(md)
    print(md)
