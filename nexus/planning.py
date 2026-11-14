"""Forecast, inventory projection, candidate actions and deterministic validation.

The model (Drex or the comparison LLM) never computes quantities: it only selects
among candidate action IDs produced and checked here. Model confidence can never
override a hard-constraint violation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .scenario import PLANNING_HORIZON_DAYS, Product, Scenario

EXPEDITE_DAYS = 2
EXPEDITE_FEE_PER_CASE = 2.50


# ---------------------------------------------------------------- forecast
def forecast(product: Product, horizon: int = PLANNING_HORIZON_DAYS) -> list[float]:
    """Seasonal-naive: mean of the same weekday in the last two weeks of history.
    Uses only history available at the planning date."""
    hist = product.demand_history
    n = len(hist)
    out = []
    for h in range(horizon):
        same = [hist[n - 7 + (h % 7)], hist[n - 14 + (h % 7)]] if n >= 14 else hist[-7:]
        out.append(sum(same) / len(same))
    return out


def receipts_by_day(product: Product, horizon: int, extra: dict[int, int] | None = None) -> list[int]:
    r = [0] * horizon
    for o in product.open_orders:
        if 0 <= o.arrival_day < horizon:
            r[o.arrival_day] += o.qty_cases
    for d, q in (extra or {}).items():
        if 0 <= d < horizon:
            r[d] += q
    return r


def project(product: Product, horizon: int = PLANNING_HORIZON_DAYS, extra: dict[int, int] | None = None,
            open_orders_override: list | None = None) -> dict:
    """Day-by-day projection. Inventory conservation: end = start + receipts - fulfilled.
    Unmet demand is tracked separately (never negative stock)."""
    fc = forecast(product, horizon)
    if open_orders_override is not None:
        saved = product.open_orders
        product.open_orders = open_orders_override
        rec = receipts_by_day(product, horizon, extra)
        product.open_orders = saved
    else:
        rec = receipts_by_day(product, horizon, extra)
    inv = float(product.available)
    rows, unmet, first_short = [], 0.0, None
    for d in range(horizon):
        start = inv
        inv += rec[d]
        fulfilled = min(inv, fc[d])
        short = fc[d] - fulfilled
        inv -= fulfilled
        unmet += short
        if short > 1e-9 and first_short is None:
            first_short = d
        rows.append({"day": d, "start": round(start, 1), "receipts": rec[d], "demand": round(fc[d], 1),
                     "fulfilled": round(fulfilled, 1), "unmet": round(short, 1), "end": round(inv, 1)})
    return {"rows": rows, "unmet": round(unmet, 1), "first_shortage_day": first_short, "ending": round(inv, 1),
            "total_demand": round(sum(fc), 1), "total_receipts": sum(rec)}


def net_need(product: Product, horizon: int = PLANNING_HORIZON_DAYS) -> int:
    p = project(product, horizon)
    need = p["total_demand"] + product.safety_stock - product.available - p["total_receipts"]
    # also cover near-term gaps that later receipts arrive too late to prevent
    return max(0, math.ceil(need), math.ceil(p["unmet"]))


# ---------------------------------------------------------------- candidates
def round_qty(need: int, moq: int, pack: int) -> int:
    q = max(need, moq)
    return int(math.ceil(q / pack) * pack)


@dataclass
class Candidate:
    id: str
    kind: str  # BUY|SPLIT|EXPEDITE|WAIT|REQUEST_INFO|ESCALATE
    lines: list[dict] = field(default_factory=list)  # [{supplier_id, qty, arrival_day, unit_price}]
    cost: float = 0.0
    unmet: float = 0.0
    waste: float = 0.0
    first_shortage_day: int | None = None
    violations: list[str] = field(default_factory=list)  # hard
    warnings: list[str] = field(default_factory=list)  # soft / needs evidence
    evidence: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.violations

    def describe(self) -> str:
        if self.kind in ("WAIT", "REQUEST_INFO", "ESCALATE"):
            base = {"WAIT": "Place no new order today.",
                    "REQUEST_INFO": "Hold the order and request the missing/unverified facts from the supplier.",
                    "ESCALATE": "Escalate to a human planner (no compliant plan meets demand)."}[self.kind]
        elif self.kind == "EXPEDITE":
            l = self.lines[0]
            base = (f"EXPEDITE: pay an expedite fee of ${l['unit_price']:.2f}/case so that existing delayed order "
                    f"{l.get('order_id', '')} ({l['qty']} cases from {l['supplier_id']}, already purchased) arrives on day "
                    f"{l['arrival_day']} instead of day {l.get('from_day', '?')}. No new stock is bought. "
                    f"Fee total ${self.cost:,.0f}.")
        else:
            parts = [f"{l['qty']} cases from {l['supplier_id']} @ ${l['unit_price']:.2f}, arrives day {l['arrival_day']}"
                     for l in self.lines]
            base = f"{self.kind}: " + "; ".join(parts) + f". Cost ${self.cost:,.0f}."
        extra = f" Projected unmet demand {self.unmet:.0f} cases; expected expiry waste {self.waste:.0f} cases."
        flags = (" Warnings: " + ", ".join(self.warnings) + ".") if self.warnings else ""
        return base + extra + flags


def _waste(product: Product, lines: list[dict], proj_end_before: float) -> float:
    """Cases expected to expire: arrivals beyond what forecast demand can absorb within shelf life."""
    fc = forecast(product, 7)
    avg = sum(fc) / len(fc)
    waste = 0.0
    for l in lines:
        s = product.supplier(l["supplier_id"])
        sellable = avg * s.shelf_life_on_arrival_days - max(0.0, proj_end_before)
        waste += max(0.0, l["qty"] - max(0.0, sellable))
    return round(waste, 1)


def _evaluate(product: Product, cand: Candidate, open_orders_override=None) -> Candidate:
    extra: dict[int, int] = {}
    for l in cand.lines:
        extra[l["arrival_day"]] = extra.get(l["arrival_day"], 0) + l["qty"]
    p = project(product, extra=extra, open_orders_override=open_orders_override)
    cand.unmet, cand.first_shortage_day = p["unmet"], p["first_shortage_day"]
    base_end = project(product, open_orders_override=open_orders_override)["ending"]
    cand.waste = _waste(product, cand.lines, base_end) if cand.lines else 0.0
    return cand


def generate_candidates(scn: Scenario, product: Product) -> list[Candidate]:
    need = net_need(product)
    cands: list[Candidate] = []
    day = scn.planning_day
    if need > 0:
        for s in product.suppliers:
            q = round_qty(need, s.moq_cases, s.pack_multiple)
            c = Candidate(id=f"BUY:{s.id}", kind="BUY", lines=[{"supplier_id": s.id, "qty": q,
                          "arrival_day": day + s.lead_time_days, "unit_price": s.price_per_case}],
                          cost=round(q * s.price_per_case, 2), evidence=list(s.source_ids))
            cands.append(_evaluate(product, c))
        # split across the two lowest-price approved suppliers when one cannot cover need
        ranked = sorted([s for s in product.suppliers if s.approved and s.capacity_confirmed
                         and scn.planning_day <= s.quote_valid_until_day], key=lambda s: s.price_per_case)
        if len(ranked) >= 2 and round_qty(need, ranked[0].moq_cases, ranked[0].pack_multiple) > ranked[0].capacity_cases:
            a, b = ranked[0], ranked[1]
            qa = (a.capacity_cases // a.pack_multiple) * a.pack_multiple
            qb = round_qty(max(0, need - qa), b.moq_cases, b.pack_multiple)
            c = Candidate(id=f"SPLIT:{a.id}+{b.id}", kind="SPLIT", lines=[
                {"supplier_id": a.id, "qty": qa, "arrival_day": day + a.lead_time_days, "unit_price": a.price_per_case},
                {"supplier_id": b.id, "qty": qb, "arrival_day": day + b.lead_time_days, "unit_price": b.price_per_case}],
                cost=round(qa * a.price_per_case + qb * b.price_per_case, 2), evidence=a.source_ids + b.source_ids)
            cands.append(_evaluate(product, c))
    for o in product.open_orders:
        if o.status == "delayed":
            s = product.supplier(o.supplier_id)
            new_arr = max(day + 1, o.arrival_day - EXPEDITE_DAYS)
            override = [oo for oo in product.open_orders if oo.id != o.id]
            c = Candidate(id=f"EXPEDITE:{o.id}", kind="EXPEDITE",
                          lines=[{"supplier_id": s.id, "qty": o.qty_cases, "arrival_day": new_arr,
                                  "unit_price": EXPEDITE_FEE_PER_CASE, "order_id": o.id,
                                  "from_day": o.arrival_day}],
                          cost=round(o.qty_cases * EXPEDITE_FEE_PER_CASE, 2), evidence=list(s.source_ids))
            cands.append(_evaluate(product, c, open_orders_override=override))
    for kind in ("WAIT", "REQUEST_INFO", "ESCALATE"):
        cands.append(_evaluate(product, Candidate(id=kind, kind=kind)))
    for c in cands:
        validate(scn, product, c)
    return cands


# ---------------------------------------------------------------- validation
def validate(scn: Scenario, product: Product, c: Candidate) -> Candidate:
    """Deterministic hard checks (violations) and evidence warnings."""
    v, w = [], []
    total = 0.0
    for l in c.lines:
        s = product.supplier(l["supplier_id"])
        if c.kind == "EXPEDITE":
            total += l["qty"] * l["unit_price"]
            continue
        if not s.approved:
            v.append(f"{s.id}: supplier not approved for {product.id}")
        if scn.planning_day > s.quote_valid_until_day:
            v.append(f"{s.id}: quote expired (valid until day {s.quote_valid_until_day})")
        if l["qty"] < s.moq_cases:
            v.append(f"{s.id}: qty {l['qty']} below MOQ {s.moq_cases}")
        if l["qty"] % s.pack_multiple:
            v.append(f"{s.id}: qty {l['qty']} not a multiple of pack {s.pack_multiple}")
        if l["qty"] > s.capacity_cases:
            v.append(f"{s.id}: qty {l['qty']} exceeds capacity {s.capacity_cases}")
        if s.shelf_life_on_arrival_days < product.min_shelf_life_at_receipt_days:
            v.append(f"{s.id}: shelf life on arrival {s.shelf_life_on_arrival_days}d < required "
                     f"{product.min_shelf_life_at_receipt_days}d")
        if l["arrival_day"] >= PLANNING_HORIZON_DAYS:
            v.append(f"{s.id}: arrives after planning horizon")
        if not s.capacity_confirmed:
            w.append(f"{s.id}: capacity not confirmed in writing")
        dup = [o for o in product.open_orders if o.supplier_id == s.id and o.status in ("ordered", "acknowledged")
               and o.arrival_day < PLANNING_HORIZON_DAYS]
        if dup and net_need(product) == 0:
            v.append(f"{s.id}: duplicate - open order {dup[0].id} already covers demand")
        total += l["qty"] * l["unit_price"]
    if c.lines and c.kind != "EXPEDITE":
        extra: dict[int, int] = {}
        for l in c.lines:
            extra[l["arrival_day"]] = extra.get(l["arrival_day"], 0) + l["qty"]
        peak = max(r["start"] + r["receipts"] for r in project(product, extra=extra)["rows"])
        if peak > scn.storage_capacity_cases:
            v.append(f"peak stock {peak:.0f} cases exceeds storage capacity {scn.storage_capacity_cases}")
    if total > scn.budget_usd:
        v.append(f"cost ${total:,.0f} exceeds budget ${scn.budget_usd:,.0f}")
    if c.lines and c.waste > 0.25 * sum(l["qty"] for l in c.lines):
        w.append(f"high expiry waste ({c.waste:.0f} cases)")
    for conflict in scn.conflicts:
        if any(sid in conflict for sid in [l["supplier_id"] for l in c.lines]):
            w.append(f"conflicting evidence: {conflict}")
    c.violations, c.warnings = v, w
    return c


def allowed_options(cands: list[Candidate]) -> list[Candidate]:
    """Only hard-valid candidates are offered to the decision model."""
    return [c for c in cands if c.valid]


# ---------------------------------------------------------------- outcome scoring on held-out actual demand
SHORTAGE_PENALTY_PER_CASE = 30.0  # assumed lost margin + service penalty (simulated)
HOLDING_COST_PER_CASE_DAY = 0.05  # assumed (simulated)


def simulate_outcome(product: Product, chosen: Candidate | None) -> dict | None:
    """Replay the chosen action against the ACTUAL next-14-day demand (never visible to the planner).
    Only the immediate action is simulated: REQUEST_INFO / ESCALATE / WAIT place no order today."""
    actual = product.actual_demand
    if not actual:
        return None
    horizon = min(len(actual), PLANNING_HORIZON_DAYS)
    orders = list(product.open_orders)
    extra: dict[int, int] = {}
    for l in (chosen.lines if chosen else []):
        if chosen.kind == "EXPEDITE":
            orders = [o for o in orders if o.id != l.get("order_id")]
        extra[l["arrival_day"]] = extra.get(l["arrival_day"], 0) + l["qty"]
    saved, product.open_orders = product.open_orders, orders
    rec = receipts_by_day(product, horizon, extra)
    product.open_orders = saved
    inv, unmet, fulfilled, holding = float(product.available), 0.0, 0.0, 0.0
    for d in range(horizon):
        inv += rec[d]
        f = min(inv, actual[d])
        unmet += actual[d] - f
        fulfilled += f
        inv -= f
        holding += inv * HOLDING_COST_PER_CASE_DAY
    demand = sum(actual[:horizon])
    spend = chosen.cost if chosen else 0.0
    return {"fill_rate": round(fulfilled / demand, 4) if demand else 1.0, "unmet_cases": round(unmet, 1),
            "ending_inventory": round(inv, 1), "spend_usd": round(spend, 2),
            "total_cost_usd": round(spend + unmet * SHORTAGE_PENALTY_PER_CASE + holding, 2)}
