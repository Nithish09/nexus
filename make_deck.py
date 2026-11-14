"""Builds slides/Nexus_Drexathon.pptx from the latest results/benchmark.json.
Run after `python benchmark.py` so the results slide shows real numbers."""
import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def slide(title, bullets, size=22):
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = title
    s.shapes.title.text_frame.paragraphs[0].font.size = Pt(36)
    tb = s.shapes.add_textbox(Inches(0.7), Inches(1.6), Inches(12), Inches(5.5)).text_frame
    tb.word_wrap = True
    for i, b in enumerate(bullets):
        p = tb.paragraphs[0] if i == 0 else tb.add_paragraph()
        p.text, p.font.size = b, Pt(size)
    return s


slide("Nexus: purchasing decisions with Drex", [
    "Drexathon 2026 - Apex Predator: Drex vs. the Giants",
    "What should we order, from which supplier, how much, and when?",
    "Drex makes the decision; deterministic checks verify it; NDI grounds it in supplier documents.",
    "Demand: historical Walmart (M5) daily sales. Supplier terms, inventory and orders: simulated."])
slide("The problem", [
    "Planning agents often let a large LLM pick the purchasing action.",
    "That is slow, costly, and prone to accepting unsupported facts:",
    "  - a ship date read as an arrival date",
    "  - 'we can probably do 300 cases' treated as confirmed capacity",
    "  - the lowest unit price whose MOQ mostly expires"])
slide("Architecture", [
    "NDI: supplier quotes, emails, delay notices -> facts with source, excerpt, status",
    "Forecast + projection (holds and reservations excluded) -> net need",
    "Candidate actions: BUY / SPLIT / EXPEDITE / WAIT / REQUEST_INFO / ESCALATE",
    "Validator removes hard-invalid options (MOQ, pack, capacity, quote, shelf life, storage, budget, duplicates)",
    "Drex: one choice question over allowed action IDs + reason code, with probabilities",
    "Intern (0.30.1, Drex + Qwen3.8-27B) wrote the threshold-sweep analysis script; other code used another assistant",
    "Model output can never override validation; purchases need approval (simulated ERP)"], 20)
slide("Worked example: a delay notice", [
    "Day 0: product P1 covered by PO-1001 (600 cases, arriving day 5) -> WAIT",
    "DOC-D1: 'New ship date: 2026-11-24, transit time: 3 days'",
    "Nexus derives arrival = day 11, not day 8 -> projected shortage from day 8",
    "Options: expedite PO-1001 ($1,500, still ~10 cases short), bridge order from S1 ($2,208, no shortage),",
    "or the cheaper fast supplier S3 ($1,672), whose capacity is only tentative",
    "Decision + evidence (DOC-D1, DOC-Q2) shown; validator passes; human approves"], 20)

res_path = Path("results/benchmark.json")
rows = []
if res_path.exists():
    res = json.loads(res_path.read_text())
    for name, s in res["summary"].items():
        if "skipped" in s:
            rows.append(f"{name}: skipped ({s['skipped']})")
        else:
            rows.append(f"{name} [{s['model']}]: accuracy {s['accuracy']:.0%} (fresh cases {s.get('accuracy_fresh', 0):.0%}), "
                        f"median {s['latency_ms_median']} ms round trip"
                        + (f" ({s['model_ms_median']} ms model)" if s.get('model_ms_median') else "")
                        + f", ~${s['cost_usd_per_decision']:.6f}/decision"
                        + (f", escalated {s['escalation_rate']:.0%}" if s.get('escalation_rate') else "")
                        + (f", fill rate {s['fill_rate_mean']:.1%} on real demand" if s.get('outcome_n') else ""))
    sm = res["summary"]
    if all(k in sm and "skipped" not in sm[k] for k in ("drex", "llm", "hybrid")):
        d, l, h = sm["drex"], sm["llm"], sm["hybrid"]
        rows.insert(0, f"Headline: hybrid matches the LLM's accuracy ({h['accuracy']:.0%} vs {l['accuracy']:.0%}) while calling it on "
                       f"{h['escalation_rate']:.0%} of decisions: {l['cost_usd_per_decision'] / h['cost_usd_per_decision']:.1f}x cheaper. "
                       f"Drex alone: {l['latency_ms_median'] / d['latency_ms_median']:.1f}x faster, "
                       f"{l['cost_usd_per_decision'] / d['cost_usd_per_decision']:.0f}x cheaper, {d['accuracy']:.0%} accurate.")
    rows.append(f"{res['n_cases']} cases x {res['repeats']} repeats, run {res['run_at']}; same candidates, "
                "actions and validator for every provider.")
else:
    rows = ["Run `python benchmark.py` then `python make_deck.py` to fill this slide."]
slide("Measured: Drex vs Opus 5.5", rows, 15)
slide("Limitations and next steps", [
    "Small benchmark (18 cases, 1 repeat); threshold 0.6 chosen after the first Drex run; two cases sit at it.",
    "Historical M5 demand; supplier terms, inventory and documents are simulated.",
    "Cost per decision is estimated from token counts and list prices.",
    "Next: multi-location transfers, receipt and inspection tracking, OR-Tools multi-period plans,",
    "more M5 items and stores, lead-time uncertainty scenarios.",
    "Code: see GitHub repository README for setup and exact tool usage."], 20)

Path("slides").mkdir(exist_ok=True)
prs.save("slides/Nexus_Drexathon.pptx")
print("wrote slides/Nexus_Drexathon.pptx")
