"""Builds slides/Nexus_Drexathon.pptx from results/benchmark_final_vs_opus55.json (real run results).

    python make_deck.py

Optional: put an image at slides/cover.png (for example one made in Adobe Firefly / Express) and it is
placed on the title slide. Nothing here claims a tool was used unless the file is actually there.
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

RES = Path("results/benchmark_final_vs_opus55.json")
if not RES.exists():
    RES = Path("results/benchmark.json")
S = json.loads(RES.read_text())["summary"]
D, H, L, R = S["drex"], S["hybrid"], S["llm"], S["rule-baseline"]
LLM_NAME = "Opus 5.5" if "opus-5-5" in L["model"] else L["model"].split("/")[-1]

BG, CARD, INK, MUTE = RGBColor(0x0B, 0x12, 0x20), RGBColor(0x16, 0x21, 0x36), RGBColor(0xF8, 0xFA, 0xFC), RGBColor(0x94, 0xA3, 0xB8)
TEAL, AMBER, VIOLET, GRAY, RED = (RGBColor(0x2D, 0xD4, 0xBF), RGBColor(0xF5, 0x9E, 0x0B), RGBColor(0xA7, 0x8B, 0xFA),
                                  RGBColor(0x64, 0x74, 0x8B), RGBColor(0xF8, 0x71, 0x71))

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def text(slide, x, y, w, h, s, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT):
    tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    for i, line in enumerate(s if isinstance(s, list) else [s]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = line, Pt(size), bold, color, "Helvetica Neue"
        p.space_after = Pt(6)
    return tf


def box(slide, x, y, w, h, fill=CARD, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    b = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    b.fill.solid()
    b.fill.fore_color.rgb = fill
    if line is None:
        b.line.fill.background()
    else:
        b.line.color.rgb, b.line.width = line, Pt(1.5)
    b.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        b.adjustments[0] = 0.08
    return b


def new(title, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    box(s, 0.6, 0.62, 0.12, 0.62, TEAL, shape=MSO_SHAPE.RECTANGLE)
    text(s, 0.9, 0.5, 11.8, 0.9, title, 32, bold=True)
    if kicker:
        text(s, 0.9, 1.25, 11.8, 0.5, kicker, 16, MUTE)
    return s


def card(slide, x, y, w, h, head, body, accent=TEAL, body_size=14):
    box(slide, x, y, w, h)
    box(slide, x, y, w, 0.08, accent, shape=MSO_SHAPE.RECTANGLE)
    text(slide, x + 0.2, y + 0.2, w - 0.4, 0.5, head, 17, accent, True)
    text(slide, x + 0.2, y + 0.8, w - 0.4, h - 0.9, body, body_size)


def stat(slide, x, y, w, big, label, color):
    box(slide, x, y, w, 1.75)
    text(slide, x + 0.1, y + 0.12, w - 0.2, 0.9, big, 44, color, True, PP_ALIGN.CENTER)
    text(slide, x + 0.15, y + 1.02, w - 0.3, 0.7, label, 13, MUTE, align=PP_ALIGN.CENTER)


def bar(slide, x, y, w, h, title, cats, vals, colors, fmt):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series(title, vals)
    ch = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    ch.has_legend, ch.has_title = False, True
    ch.chart_title.text_frame.text = title
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = INK
    plot = ch.plots[0]
    plot.gap_width, plot.has_data_labels = 60, True
    plot.data_labels.number_format, plot.data_labels.number_format_is_linked = fmt, False
    plot.data_labels.font.size, plot.data_labels.font.color.rgb = Pt(12), INK
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, c in enumerate(colors[:len(cats)]):
        pt = plot.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = c
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    ch.category_axis.tick_labels.font.size, ch.category_axis.tick_labels.font.color.rgb = Pt(12), INK
    ch.category_axis.format.line.color.rgb = GRAY
    ch.category_axis.reverse_order = True


speed = L["latency_ms_median"] / D["latency_ms_median"]
cheap = L["cost_usd_per_decision"] / D["cost_usd_per_decision"]
hcheap = L["cost_usd_per_decision"] / H["cost_usd_per_decision"]

# 1 ---------------------------------------------------------------- title
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = BG
cover = Path("slides/cover.png")
if cover.exists():
    s.shapes.add_picture(str(cover), Inches(7.4), Inches(0), height=Inches(7.5))
box(s, 0.8, 1.0, 4.2, 0.42, TEAL)
text(s, 0.8, 1.05, 4.2, 0.4, "DREXATHON 2026  ·  APEX PREDATOR", 11, BG, True, PP_ALIGN.CENTER)
text(s, 0.8, 1.9, 6.6, 1.4, "Nexus", 80, bold=True)
text(s, 0.8, 3.3, 6.4, 1.2, "Supply-chain purchasing decisions, made by Drex and checked by rules.", 24, MUTE)
text(s, 0.8, 4.9, 6.4, 1.6, [f"Drex vs {LLM_NAME}: {speed:.1f}x faster, ~{cheap:.0f}x cheaper.",
                             f"Drex + {LLM_NAME} on {H['escalation_rate']:.0%} of decisions: same accuracy as {LLM_NAME} alone."],
     18, TEAL, True)
text(s, 0.8, 6.7, 9, 0.4, "Real Walmart (M5) demand  ·  simulated supplier terms and inventory", 12, MUTE)

# 2 ---------------------------------------------------------------- problem
s = new("LLM as purchasing brain: slow, costly, too trusting",
        "Three traps that planning agents fall into when a model reads supplier documents and picks the action")
card(s, 0.6, 2.1, 3.9, 3.9, "Ship date ≠ arrival date",
     ["“New ship date: Nov 24. Transit time: 3 days.”", "", "Read it as an arrival date and you plan a stockout."], AMBER)
card(s, 4.72, 2.1, 3.9, 3.9, "“Probably” is not capacity",
     ["“We can probably do 300 cases, will confirm Monday.”", "", "Treat it as confirmed and the order may never ship."], RED)
card(s, 8.84, 2.1, 3.9, 3.9, "Cheapest price, worst order",
     ["Lowest price per case, but a 600-case minimum.", "", "Most of it expires before it can be sold."], VIOLET)
text(s, 0.6, 6.3, 12, 0.6, "Nexus question: what should we order, from whom, how much and when, with evidence for every choice?", 16, INK, True)

# 3 ---------------------------------------------------------------- pipeline
s = new("How Nexus decides", "The model never invents quantities. It picks among options Nexus has already computed and checked.")
steps = [("NDI", "Reads quotes, emails, delay notices into facts with sources", AMBER),
         ("Forecast", "Real demand history → projected stock and net need", GRAY),
         ("Options", "Buy · Split · Expedite · Wait · Request info · Escalate", GRAY),
         ("Validator", "Removes options that break MOQ, capacity, shelf life, storage, budget", RED),
         ("Drex", "Picks one option + reason code, with a probability for each", TEAL),
         ("Approval", "Human approves; simulated ERP, duplicate-proof", GRAY)]
x = 0.5
for i, (h_, b_, c_) in enumerate(steps):
    box(s, x, 2.3, 1.9, 2.6, CARD, c_)
    text(s, x + 0.1, 2.45, 1.7, 0.5, h_, 18, c_ if c_ != GRAY else INK, True, PP_ALIGN.CENTER)
    text(s, x + 0.12, 3.05, 1.66, 1.8, b_, 12, INK, align=PP_ALIGN.CENTER)
    if i < len(steps) - 1:
        a = box(s, x + 1.93, 3.45, 0.2, 0.3, TEAL, shape=MSO_SHAPE.RIGHT_ARROW)
    x += 2.08
card(s, 0.5, 5.3, 6.0, 1.6, "Hybrid mode", f"Drex decides. Only when its confidence is under 60% does the same question go to {LLM_NAME}.", VIOLET, 14)
card(s, 6.75, 5.3, 6.05, 1.6, "Safety rule", "Model output can never override a failed check. An invalid choice becomes an escalation.", RED, 14)

# 4 ---------------------------------------------------------------- demo
s = new("Worked example: a delay notice arrives", "Live in the app: Run weekly plan → Supplier delay notice arrives → replan")
tl = [("Day 0", "Order PO-1001 (600 cases) arrives day 5. Stock is covered.", "WAIT", TEAL),
      ("Notice", "“New ship date Nov 24, transit 3 days” → arrival is day 11, not day 8.", "REPLAN", AMBER),
      ("Options", "Expedite $1,500 (still ~10 cases short) · Bridge order from S1 $2,208 (no shortage) · "
                  "Cheaper S3 $1,672 (capacity only tentative)", "CHOOSE", VIOLET),
      ("Check", "Validator passes the choice; a person approves; evidence links to the source documents.", "APPROVE", TEAL)]
y = 2.0
for h_, b_, tag, c_ in tl:
    box(s, 0.6, y, 12.1, 1.08)
    box(s, 0.6, y, 0.1, 1.08, c_, shape=MSO_SHAPE.RECTANGLE)
    text(s, 0.9, y + 0.3, 1.5, 0.5, h_, 18, c_, True)
    text(s, 2.4, y + 0.17, 8.3, 0.9, b_, 14)
    box(s, 10.95, y + 0.32, 1.5, 0.44, c_)
    text(s, 10.95, y + 0.36, 1.5, 0.4, tag, 12, BG, True, PP_ALIGN.CENTER)
    y += 1.22

# 5 ---------------------------------------------------------------- results
s = new(f"Measured: Drex vs {LLM_NAME}", "18 decision cases · same options, same checks for every provider · run on Nov 14, 2026")
stat(s, 0.6, 1.95, 2.9, f"{speed:.1f}x", f"faster than {LLM_NAME}\n(median {D['latency_ms_median']:.0f} ms vs {L['latency_ms_median']:.0f} ms)", TEAL)
stat(s, 3.7, 1.95, 2.9, f"~{cheap:.0f}x", f"cheaper per decision\n(${D['cost_usd_per_decision']:.6f} vs ${L['cost_usd_per_decision']:.4f})", TEAL)
stat(s, 6.8, 1.95, 2.9, f"{H['accuracy']:.0%}", f"hybrid accuracy, same as {LLM_NAME}\n(LLM used on {H['escalation_rate']:.0%} of decisions)", VIOLET)
stat(s, 9.9, 1.95, 2.9, f"{hcheap:.1f}x", f"hybrid is cheaper than\n{LLM_NAME} alone", VIOLET)
names = ["Drex alone", "Hybrid", f"{LLM_NAME} alone", "Fixed rules"]
cols = [TEAL, VIOLET, AMBER, GRAY]
bar(s, 0.5, 3.95, 4.2, 3.3, "Accuracy (18 cases)", names, [D["accuracy"], H["accuracy"], L["accuracy"], R["accuracy"]], cols, "0%")
bar(s, 4.6, 3.95, 4.2, 3.3, "Median latency (ms)", names[:3], [D["latency_ms_median"], H["latency_ms_median"], L["latency_ms_median"]], cols, "#,##0")
bar(s, 8.7, 3.95, 4.2, 3.3, "Cost per 1,000 decisions (USD)", names[:3],
    [1000 * D["cost_usd_per_decision"], 1000 * H["cost_usd_per_decision"], 1000 * L["cost_usd_per_decision"]], cols, "$0.00")

# 6 ---------------------------------------------------------------- confidence
s = new("Drex knows when it is unsure", "Why the hybrid works: Drex's misses mostly came with low confidence")
card(s, 0.6, 2.0, 5.9, 2.35, "3 of 4 Drex misses: low confidence",
     ["Those three were under 60% confidence; escalating them to " + LLM_NAME + " fixed all three.",
      f"The fourth miss is the same answer {LLM_NAME} gave (a debatable label)."], TEAL)
card(s, 0.6, 4.55, 5.9, 2.35, "Models beat fixed rules on evidence",
     ["Rules miss conflicting notices, a tentative “may slip” email and an unnecessary expedite fee.",
      "Drex alone gets all three right."], AMBER)
box(s, 6.8, 2.0, 5.95, 4.9)
text(s, 7.0, 2.12, 5.5, 0.5, "Threshold sweep (script written with Intern)", 16, VIOLET, True)
rows = [("Escalate below", "Sent to LLM", "Accuracy"), ("40%", "0%", "78%"), ("50%", "6%", "83%"), ("60%", "22%", "94%"),
        ("70%", "39%", "94%"), ("80%", "44%", "94%"), ("90%", "61%", "94%")]
sweep = Path("results/threshold_sweep.json")
yy = 2.75
for i, r_ in enumerate(rows):
    hl = r_[0] == "60%"
    if hl:
        box(s, 6.95, yy - 0.04, 5.65, 0.5, RGBColor(0x2A, 0x24, 0x55))
    for j, cell in enumerate(r_):
        text(s, 7.1 + j * 1.9, yy, 1.8, 0.45, cell, 15 if i else 13, MUTE if i == 0 else (VIOLET if hl else INK), bold=hl)
    yy += 0.55
text(s, 7.0, 6.45, 5.6, 0.4, "In-sample, one run: 60% is the lowest setting that reaches the LLM's accuracy.", 11, MUTE)

# 6b --------------------------------------------------------------- exploratory redesign
EXP = Path("results/benchmark_exploratory_drex_evidence.json")
if EXP.exists():
    E = json.loads(EXP.read_text())["summary"]["drex-evidence"]
    s = new("What we learned: let Drex judge evidence, let code do the math",
            "Exploratory redesign, run on the same 18 cases after seeing their results. In-sample, not a held-out score.")
    stat(s, 0.6, 1.95, 2.9, f"{round(E['accuracy'] * 18)}/18", "correct on the same 18 cases\n(in-sample)", TEAL)
    stat(s, 3.7, 1.95, 2.9, f"{E['latency_ms_median']:.0f} ms", f"median per decision\n({LLM_NAME}: {L['latency_ms_median']:.0f} ms)", TEAL)
    stat(s, 6.8, 1.95, 2.9, f"~{L['cost_usd_per_decision'] / E['cost_usd_per_decision']:.0f}x", f"cheaper than {LLM_NAME}\n(${E['cost_usd_per_decision']:.6f} per decision)", TEAL)
    stat(s, 9.9, 1.95, 2.9, "0", f"calls to {LLM_NAME}", VIOLET)
    card(s, 0.6, 4.0, 3.9, 2.9, "Before: one big question",
         ["Drex chose among 6-7 options using five priority rules in a single pass.",
          "It turned cautious whenever any option carried a warning: 14/18."], AMBER, 13)
    card(s, 4.72, 4.0, 3.9, 2.9, "After: one narrow question",
         ["“Does existing supply depend on a tentative or contradicted fact?”",
          "Drex answers that; code compares shortage and cost and picks the action."], TEAL, 13)
    card(s, 8.84, 4.0, 3.9, 2.9, "Read this carefully",
         ["Drex's answer changes the outcome in the 4 cases where supply looks sufficient; code decides the rest.",
          "Designed after seeing these cases. Needs new cases to validate."], RED, 13)

# 7 ---------------------------------------------------------------- honest limits
s = new("What is real, what is simulated, what is next")
card(s, 0.6, 1.8, 3.9, 3.3, "Real", ["Walmart daily sales (M5 dataset), 3 items, 4 California stores.",
                                     "Fresh cases are scored against the real sales of the next 14 days.",
                                     "Live Drex and " + LLM_NAME + " calls."], TEAL, 13)
card(s, 4.72, 1.8, 3.9, 3.3, "Simulated", ["Supplier quotes, prices, lead times, inventory, orders, documents.",
                                          "Product names are illustrative.",
                                          "Cost penalties in outcome scoring are assumptions."], AMBER, 13)
card(s, 8.84, 1.8, 3.9, 3.3, "Next", ["Multi-location transfers and receipt tracking.",
                                     "More M5 items and stores, larger case set.",
                                     "Lead-time uncertainty scenarios."], VIOLET, 13)
text(s, 0.6, 5.4, 12.2, 0.5, "Built with", 14, MUTE, True)
text(s, 0.6, 5.8, 12.2, 1.2, ["Drex Max v1.1 (every decision)  ·  NDI Extract via nace-sdk (supplier documents)  ·  DeepInfra (" + LLM_NAME + ")  ·  "
                              "Intern 0.30.1 (threshold-sweep script)"], 14)

Path("slides").mkdir(exist_ok=True)
prs.save("slides/Nexus_Drexathon.pptx")
print("wrote slides/Nexus_Drexathon.pptx")
