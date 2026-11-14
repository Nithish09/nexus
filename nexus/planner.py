"""Planning run: Demand & Inventory -> Supplier Assessment -> Procurement Planning ->
Drex decision -> Verification & Approval -> (simulated) Execution ledger."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .decide import REASON_CODES, DecisionResult, build_state
from .planning import Candidate, allowed_options, generate_candidates, net_need, project, simulate_outcome
from .scenario import Product, Scenario

DB_PATH = Path(__file__).resolve().parent.parent / "results" / "nexus.db"


@dataclass
class ProductPlan:
    product_id: str
    product_name: str
    need: int
    projection: dict
    candidates: list[Candidate]
    options: list[Candidate]
    state: str
    decision: DecisionResult
    final_action: str
    verification: list[str] = field(default_factory=list)
    explanation: str = ""
    outcome: dict | None = None  # scored on held-out actual demand


def product_header(scn: Scenario, p: Product) -> dict:
    proj = project(p)
    return {
        "planning_day": scn.planning_day, "location": scn.location, "product": f"{p.id} {p.name} ({p.unit})",
        "on_hand": p.on_hand, "reserved": p.reserved, "quality_hold": p.quality_hold,
        "available_after_reservations_and_holds": p.available, "safety_stock": p.safety_stock,
        "forecast_demand_14d": proj["total_demand"], "open_orders": [
            f"{o.id} {o.qty_cases} cases from {o.supplier_id} arriving day {o.arrival_day} ({o.status})"
            for o in p.open_orders] or "none",
        "projected_first_shortage_day_without_new_order": proj["first_shortage_day"],
        "net_need_cases": net_need(p), "budget_usd": scn.budget_usd,
        "storage_capacity_cases": scn.storage_capacity_cases,
        "min_shelf_life_at_receipt_days": p.min_shelf_life_at_receipt_days,
    }


def plan_product(scn: Scenario, p: Product, provider) -> ProductPlan:
    cands = generate_candidates(scn, p)
    options = allowed_options(cands)
    facts = [f for f in scn.facts if f.get("product") in (None, p.id)]
    state = build_state(product_header(scn, p), facts, scn.missing, scn.conflicts)
    decision = provider.decide(state, options)
    # Verification & Approval: model output can never override validation.
    verification, final = [], decision.action
    chosen = next((c for c in cands if c.id == decision.action), None)
    if chosen is None:
        verification.append(f"REJECTED: model returned '{decision.action}', not an allowed action -> ESCALATE")
        final = "ESCALATE"
    elif not chosen.valid:
        verification.append("REJECTED: " + "; ".join(chosen.violations) + " -> ESCALATE")
        final = "ESCALATE"
    else:
        verification.append("PASSED deterministic checks (MOQ, pack, capacity, quote validity, shelf life, storage, budget, duplicates)")
        if chosen.kind in ("BUY", "SPLIT", "EXPEDITE"):
            verification.append("REQUIRES APPROVAL: purchase actions are executed only after human approval (simulated ERP)")
    chosen = next((c for c in cands if c.id == final), None)
    expl = explain(chosen, decision)
    return ProductPlan(p.id, p.name, net_need(p), project(p), cands, options, state, decision, final, verification, expl,
                       simulate_outcome(p, chosen))


def explain(c: Candidate | None, d: DecisionResult) -> str:
    if c is None:
        return "No action."
    why = REASON_CODES.get(d.reason or "", "")
    ev = f" Evidence: {', '.join(c.evidence)}." if c.evidence else ""
    return f"{c.describe()} {('Reason: ' + why) if why else ''}{ev}".strip()


def run_plan(scn: Scenario, provider) -> list[ProductPlan]:
    return [plan_product(scn, p, provider) for p in scn.products]


# ------------------------------------------------------------ simulated execution ledger (idempotent)
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS actions(
        action_key TEXT PRIMARY KEY, planning_day INT, product_id TEXT, action TEXT,
        status TEXT, payload TEXT)""")
    return con


def action_key(day: int, product_id: str, action: str) -> str:
    return hashlib.sha256(f"{day}|{product_id}|{action}".encode()).hexdigest()[:16]


def record(plan: ProductPlan, day: int, status: str = "recommended") -> tuple[str, bool]:
    """Returns (key, inserted). Re-running the same day never creates a duplicate action."""
    key = action_key(day, plan.product_id, plan.final_action)
    con = _db()
    try:
        con.execute("INSERT INTO actions VALUES (?,?,?,?,?,?)", (key, day, plan.product_id, plan.final_action, status,
                    json.dumps({"explanation": plan.explanation, "decision": plan.decision.to_dict()})))
        con.commit()
        return key, True
    except sqlite3.IntegrityError:
        return key, False
    finally:
        con.close()


def set_status(key: str, status: str):
    con = _db()
    con.execute("UPDATE actions SET status=? WHERE action_key=?", (status, key))
    con.commit()
    con.close()


def history():
    con = _db()
    rows = con.execute("SELECT action_key, planning_day, product_id, action, status FROM actions ORDER BY rowid").fetchall()
    con.close()
    return rows
