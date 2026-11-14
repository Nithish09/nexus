"""Nexus dashboard.  Run:  streamlit run app.py"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from nexus import history
from nexus.config import get_settings
from nexus.decide import get_provider
from nexus.documents import apply_delay_notice, doc_id, extract, list_documents
from nexus.planner import history, record, run_plan, set_status
from nexus.scenario import DOC_PRODUCT, demo_scenario

st.set_page_config(page_title="Nexus - supply-chain decisions with Drex", layout="wide")
S = get_settings()

# ---------------------------------------------------------------- state
if "scn" not in st.session_state:
    st.session_state.scn = demo_scenario()
    st.session_state.docs = {}
    st.session_state.before = None
    st.session_state.after = None
    st.session_state.event_log = []


def load_docs(skip=("DOC-D1",)):
    scn = st.session_state.scn
    for path in list_documents():
        did = doc_id(path)
        if did in skip or did in st.session_state.docs:
            continue
        res = extract(path, scn.planning_day)
        for f in res["facts"]:
            f["product"] = DOC_PRODUCT.get(did)
        st.session_state.docs[did] = {"path": str(path), **res}
        scn.facts.extend(res["facts"])


load_docs()

# ---------------------------------------------------------------- sidebar
st.sidebar.title("Nexus")
st.sidebar.caption("Procurement & replenishment agent. Drex makes the decisions; deterministic checks verify them.")
st.sidebar.markdown(
    f"**Drex (System 1):** {'LIVE - ' + S.drex_model if S.drex_live else 'not configured'}  \n"
    f"**Comparison LLM (System 2):** {'LIVE - ' + S.llm_model if S.llm_live else 'not configured'}  \n"
    f"**NDI documents:** {'LIVE' if S.ndi_live else 'local fallback extractor'}")
default = "drex" if S.drex_live else "rule-baseline"
provider_name = st.sidebar.selectbox("Decision provider", ["drex", "hybrid", "llm", "rule-baseline"],
                                     index=["drex", "hybrid", "llm", "rule-baseline"].index(default))
provider = get_provider(provider_name)
if provider_name != "rule-baseline" and not provider.live:
    st.sidebar.error("This provider is not configured - add keys to .env. Decisions will fail and be escalated.")
if provider_name == "rule-baseline":
    st.sidebar.info("OFFLINE DEMO MODE: decisions come from the deterministic rule baseline, not a model.")

if st.sidebar.button("1. Run weekly plan", type="primary"):
    st.session_state.before = run_plan(st.session_state.scn, provider)
    st.session_state.after = None
if st.sidebar.button("2. Supplier delay notice arrives (DOC-D1)"):
    path = next(p for p in list_documents() if doc_id(p) == "DOC-D1")
    res = extract(path, st.session_state.scn.planning_day)
    for f in res["facts"]:
        f["product"] = "P1"
    st.session_state.docs["DOC-D1"] = {"path": str(path), **res}
    changes = apply_delay_notice(st.session_state.scn, res["facts"])
    st.session_state.event_log += changes or ["DOC-D1 processed: no matching open order"]
    st.session_state.after = run_plan(st.session_state.scn, provider)
if st.sidebar.button("Reset scenario"):
    for k in ["scn", "docs", "before", "after", "event_log"]:
        st.session_state.pop(k, None)
    st.rerun()

st.title("Nexus: what should we order, from whom, and when?")
st.warning("All supplier terms, inventory, prices and orders are SIMULATED. Product names are illustrative. "
           "No real supplier transaction is ever placed.")
for _p in st.session_state.scn.products:
    st.caption(f"Demand for {_p.id} {_p.name}: {_p.demand_source}")
if history.available():
    st.caption(history.M5_NOTE)

tab_plan, tab_docs, tab_bench, tab_hist = st.tabs(["Plan & decisions", "Documents & evidence", "Drex vs LLM benchmark",
                                                   "Approvals & history"])


def show_plans(plans, title):
    st.subheader(title)
    for pl in plans:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Product", f"{pl.product_id} {pl.product_name}")
            c2.metric("Net need (cases)", pl.need)
            fs = pl.projection["first_shortage_day"]
            c3.metric("First shortage w/o new order", "none" if fs is None else f"day {fs}")
            c4.metric("Decision", pl.final_action)
            st.markdown(f"**Why:** {pl.explanation}")
            d = pl.decision
            st.caption(f"Provider: {d.provider} ({d.model}) | live={d.live} | latency {d.latency_ms:.0f} ms | "
                       f"model time {d.model_ms if d.model_ms is not None else '-'} ms | {d.input_tokens} input tokens | "
                       f"reason code: {d.reason} | est. cost ${d.cost_usd:.6f}" + (f" | ERROR: {d.error}" if d.error else ""))
            for v in pl.verification:
                (st.error if v.startswith("REJECTED") else st.success if v.startswith("PASSED") else st.info)(v)
            if d.probabilities:
                st.bar_chart(pd.Series(d.probabilities, name="probability"))
            cols = st.columns(2)
            proj = pd.DataFrame(pl.projection["rows"]).set_index("day")[["end", "demand", "receipts", "unmet"]]
            cols[0].markdown("Projected inventory without a new order")
            cols[0].line_chart(proj[["end", "demand"]])
            cand = pd.DataFrame([{"action": c.id, "offered_to_model": c.valid, "cost_usd": c.cost,
                                  "unmet_cases": c.unmet, "expiry_waste": c.waste,
                                  "violations": "; ".join(c.violations), "warnings": "; ".join(c.warnings),
                                  "evidence": ", ".join(c.evidence)} for c in pl.candidates])
            cols[1].markdown("Candidate actions (hard-invalid ones are never offered)")
            cols[1].dataframe(cand, hide_index=True, use_container_width=True)
            if pl.final_action not in ("WAIT", "ESCALATE", "REQUEST_INFO"):
                if st.button(f"Approve {pl.final_action} for {pl.product_id} (simulated ERP)", key=f"ap-{title}-{pl.product_id}"):
                    key, new = record(pl, st.session_state.scn.planning_day, "recommended")
                    if new:
                        set_status(key, "approved")
                        st.success(f"Approved and sent to simulated ERP as action {key}.")
                    else:
                        st.warning(f"Duplicate prevented: action {key} already exists for this day.")
            with st.expander("State sent to the decision model"):
                st.code(pl.state)


with tab_plan:
    if st.session_state.before is None:
        st.info("Click **1. Run weekly plan** in the sidebar.")
    else:
        if st.session_state.after is not None:
            st.markdown("### Event: " + " | ".join(st.session_state.event_log))
            diff = pd.DataFrame([{"product": b.product_id, "before": b.final_action, "after": a.final_action,
                                  "cost_before": next((c.cost for c in b.candidates if c.id == b.final_action), 0),
                                  "cost_after": next((c.cost for c in a.candidates if c.id == a.final_action), 0)}
                                 for b, a in zip(st.session_state.before, st.session_state.after)])
            st.dataframe(diff, hide_index=True)
            show_plans(st.session_state.after, "Replanned after the delay notice")
        show_plans(st.session_state.before, "Initial weekly plan")

with tab_docs:
    st.caption("Facts keep their source document, exact excerpt and status (stated / confirmed / tentative / derived). "
               "Ship dates and arrival dates are separate fields.")
    for did, info in sorted(st.session_state.docs.items()):
        with st.expander(f"{did} - {Path(info['path']).name} [{info['mode']}]"):
            st.code(Path(info["path"]).read_text())
            st.dataframe(pd.DataFrame(info["facts"]).reindex(columns=["field", "value", "status", "supplier", "excerpt", "extractor",
                                                                      "ndi_confidence", "local_value"]),
                         hide_index=True, use_container_width=True)
            if info.get("ndi"):
                st.json(info["ndi"])

with tab_bench:
    f = Path("results/benchmark.md")
    if f.exists():
        st.markdown(f.read_text())
    else:
        st.info("Run `python benchmark.py` to generate results.")
    j = Path("results/benchmark.json")
    if j.exists():
        rows = pd.DataFrame(json.loads(j.read_text())["rows"])
        st.dataframe(rows, hide_index=True, use_container_width=True)

with tab_hist:
    h = history()
    st.dataframe(pd.DataFrame(h, columns=["action_key", "planning_day", "product", "action", "status"]), hide_index=True)
    st.caption("Future work: acknowledged/shipped/received/inspected tracking, multi-location transfers, "
               "production scheduling, OR-Tools optimisation over multi-period plans.")
