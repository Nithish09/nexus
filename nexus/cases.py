"""Benchmark cases. Each case modifies the seeded scenario for product P1 and states the
expected action, specified independently from any model output (see 'why').
Split: 'dev' cases were used while building prompts; 'heldout' cases were not, but their results were
seen once before an option-wording fix; 'fresh' cases were added afterwards and never used for tuning."""
from __future__ import annotations

from .scenario import OpenOrder, Scenario, base_scenario, demand_for


def _p1_only(scn: Scenario) -> Scenario:
    scn.products = [scn.product("P1")]
    return scn


def _base(on_hand=520, reserved=40, hold=0, demand=40, holdout=False) -> Scenario:
    scn = _p1_only(base_scenario())
    p = scn.product("P1")
    p.on_hand, p.reserved, p.quality_hold = on_hand, reserved, hold
    p.demand_history, p.demand_source, p.actual_demand = demand_for(
        "P1" if demand == 40 else "P1-slow", holdout=holdout)
    return scn


def c01_normal():
    return _base()


def c02_moq_expiry_trap():
    scn = _base(on_hand=200, demand=15)
    s2 = scn.product("P1").supplier("S2")
    s2.price_per_case, s2.shelf_life_on_arrival_days = 15.00, 16
    return scn


def c03_unconfirmed_fast_capacity():
    scn = _base(on_hand=120, reserved=40)
    p = scn.product("P1")
    p.supplier("S1").lead_time_days = 4
    p.open_orders = [OpenOrder("PO-0990", "S2", 600, 4, "acknowledged")]
    return scn


def c04_split_needed():
    scn = _base(on_hand=300)
    p = scn.product("P1")
    p.supplier("S1").capacity_cases = 200
    p.supplier("S2").quote_valid_until_day = -1
    p.supplier("S3").capacity_confirmed = True
    return scn


def c05_expired_quote():
    scn = _base(on_hand=520)
    scn.product("P1").supplier("S1").quote_valid_until_day = -1
    scn.product("P1").supplier("S3").approved = False
    return scn


def c06_conflicting_delivery():
    scn = _base(on_hand=300)
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 4, "acknowledged")]
    scn.conflicts = ["S2 PO-1001: supplier confirmation says arrival day 4, carrier tracking says arrival day 10"]
    return scn


def c07_ship_vs_arrival():
    scn = _base(on_hand=440)
    # Delay notice: new SHIP date day 8 + 3 days transit => arrival day 11 (not day 8).
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 11, "delayed")]
    scn.facts = [
        {"source_id": "DOC-D1", "field": "new_ship_date", "value": "2026-11-24", "status": "stated",
         "excerpt": "New ship date: 2026-11-24"},
        {"source_id": "DOC-D1", "field": "transit_days", "value": "3", "status": "stated",
         "excerpt": "Transit time: 3 days"},
        {"source_id": "DOC-D1", "field": "new_arrival_day", "value": "11", "status": "derived",
         "excerpt": "ship 2026-11-24 (day 8) + 3 days transit"},
    ]
    return scn


def c08_quarantine():
    return _base(on_hand=700, reserved=40, hold=300)


def c09_delay_after_order():
    scn = _base(on_hand=300)
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 8, "delayed")]
    return scn


def c10_insufficient_budget():
    scn = _base()
    scn.budget_usd = 1500
    return scn


def c11_duplicate_run():
    scn = _base()
    scn.product("P1").open_orders = [OpenOrder("PO-1002", "S1", 192, 3, "ordered")]
    return scn


def c12_no_feasible_plan():
    scn = _base(on_hand=60, reserved=40)
    p = scn.product("P1")
    p.supplier("S3").approved = False
    p.supplier("S1").capacity_cases = 100
    return scn


# ---- Fresh cases, added after the first live Drex run and never used to adjust prompts or wording.
# They plan on history that ends 14 days before the end of the M5 data, so each decision can also be
# scored against the real sales of the following 14 days.
def c13_storage_limit():
    scn = _base(holdout=True)
    scn.storage_capacity_cases = 700
    p = scn.product("P1")
    p.supplier("S1").approved = False
    p.supplier("S3").capacity_confirmed = True
    return scn


def c14_cheaper_but_unconfirmed():
    scn = _base(holdout=True)
    scn.product("P1").supplier("S3").price_per_case = 16.00
    return scn


def c15_harmless_delay():
    scn = _base(on_hand=560, holdout=True)
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 8, "delayed")]
    return scn


def c16_tentative_delay_warning():
    scn = _base(on_hand=300, holdout=True)
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 4, "acknowledged")]
    scn.facts = [{"source_id": "EMAIL-S2-17", "field": "possible_delay", "value": "up to 7 days", "status": "tentative",
                  "excerpt": "PO-1001 may slip by up to a week because of a line fault; we will confirm tomorrow."}]
    return scn


def c17_expedite_not_enough():
    scn = _base(on_hand=380, holdout=True)
    scn.product("P1").open_orders = [OpenOrder("PO-1001", "S2", 600, 11, "delayed")]
    return scn


def c18_waste_or_unverified():
    scn = _base(on_hand=200, demand=15, holdout=True)
    p = scn.product("P1")
    p.supplier("S1").approved = False
    s2 = p.supplier("S2")
    s2.price_per_case, s2.shelf_life_on_arrival_days = 15.00, 16
    return scn


# ---- Blind validation set: written AFTER the drex-evidence design was frozen, on a different product
# (P2, M5 item FOODS_3_586, different suppliers). Expected answers were fixed before any model saw them,
# and no prompt, threshold or code was changed after they were run.
def _base2(on_hand=150, reserved=10, hold=20) -> Scenario:
    scn = base_scenario()
    scn.products = [scn.product("P2")]
    p = scn.product("P2")
    p.on_hand, p.reserved, p.quality_hold = on_hand, reserved, hold
    p.demand_history, p.demand_source, p.actual_demand = demand_for("P2", holdout=True)
    return scn


def n01_plain_order():
    return _base2()


def n02_open_order_covers():
    scn = _base2(on_hand=130)
    scn.product("P2").open_orders = [OpenOrder("PO-2001", "S5", 300, 3, "acknowledged")]
    return scn


def n03_conflicting_arrival():
    scn = n02_open_order_covers()
    scn.conflicts = ["PO-2001: supplier portal shows delivery on day 3, the carrier's tracking page shows day 9"]
    return scn


def n04_confirmed_on_schedule():
    scn = n02_open_order_covers()
    scn.facts = [{"source_id": "EMAIL-S5-41", "field": "shipment_status", "value": "on schedule", "status": "confirmed",
                  "excerpt": "PO-2001 left our dock this morning; carrier confirms delivery on day 3 as planned."}]
    return scn


def n05_irrelevant_tentative_note():
    scn = n02_open_order_covers()
    scn.facts = [{"source_id": "EMAIL-S6-12", "field": "future_price", "value": "may rise", "status": "tentative",
                  "excerpt": "Heads up: our list price for next quarter may go up a little, we will confirm in January."}]
    return scn


def n06_harmful_delay():
    scn = _base2(on_hand=130)
    scn.product("P2").open_orders = [OpenOrder("PO-2001", "S5", 300, 7, "delayed")]
    return scn


def n07_hold_might_be_released():
    scn = _base2(on_hand=310, hold=200)
    scn.facts = [{"source_id": "QA-NOTE-7", "field": "hold_release", "value": "possible", "status": "tentative",
                  "excerpt": "The 200 cases on quality hold might be released tomorrow if the lab result is clean."}]
    return scn


def n08_expired_cheaper_quote():
    scn = _base2(on_hand=190)
    scn.product("P2").supplier("S4").quote_valid_until_day = -1
    return scn


def n09_supplier_not_sure():
    scn = n02_open_order_covers()
    scn.facts = [{"source_id": "EMAIL-S5-44", "field": "ship_confidence", "value": "uncertain", "status": "tentative",
                  "excerpt": "We think PO-2001 can still ship this week but the bottling line is down; "
                             "we cannot promise the day-3 delivery yet."}]
    return scn


def n10_budget_too_small():
    scn = _base2()
    scn.budget_usd = 2000
    return scn


CASES = [
    # id, builder, expected, split, why
    ("C01", c01_normal, "BUY:S1", "dev", "Cheapest compliant order that covers demand; S3 capacity unverified."),
    ("C02", c02_moq_expiry_trap, "BUY:S1", "dev", "S2 has the lowest unit price but its 600-case MOQ would mostly expire."),
    ("C03", c03_unconfirmed_fast_capacity, "REQUEST_INFO", "dev",
     "Only S3 arrives before the stockout, but its capacity is tentative; confirm before ordering."),
    ("C04", c04_split_needed, "SPLIT:S1+S3", "heldout", "S1 capacity is too small and S2's quote expired; split S1+S3."),
    ("C05", c05_expired_quote, "BUY:S2", "dev", "S1's quote has expired and S3 is not approved; S2 covers demand without a shortage."),
    ("C06", c06_conflicting_delivery, "REQUEST_INFO", "heldout",
     "Supply looks sufficient only if the disputed day-4 arrival is true; resolve the conflict first."),
    ("C07", c07_ship_vs_arrival, "EXPEDITE:PO-1001", "heldout",
     "Ship date is not arrival date: day 11 arrival causes a shortage; expediting recovers it cheaply."),
    ("C08", c08_quarantine, "BUY:S1", "dev", "On-hand looks high but 300 cases are on quality hold."),
    ("C09", c09_delay_after_order, "EXPEDITE:PO-1001", "heldout",
     "Placed order slipped to day 8; expediting avoids the gap more cheaply than a new order."),
    ("C10", c10_insufficient_budget, "ESCALATE", "dev", "Every compliant order exceeds the purchasing budget."),
    ("C11", c11_duplicate_run, "WAIT", "heldout", "Today's order PO-1002 already covers demand; do not duplicate."),
    ("C12", c12_no_feasible_plan, "ESCALATE", "heldout", "No compliant option can avoid a shortage."),
    ("C13", c13_storage_limit, "BUY:S3", "fresh", "S2's 600-case order would exceed warehouse storage; S3 is confirmed here."),
    ("C14", c14_cheaper_but_unconfirmed, "BUY:S1", "fresh",
     "S3 is cheaper but its capacity is unconfirmed; S1 is verified and covers demand."),
    ("C15", c15_harmless_delay, "WAIT", "fresh", "The order is delayed but still arrives before any shortage; no fee needed."),
    ("C16", c16_tentative_delay_warning, "REQUEST_INFO", "fresh",
     "Supply is sufficient only if a tentatively reported slip does not happen; confirm before deciding."),
    ("C17", c17_expedite_not_enough, "BUY:S1", "fresh",
     "Expediting still leaves a shortage; a verified bridge order removes it."),
    ("C18", c18_waste_or_unverified, "REQUEST_INFO", "fresh",
     "The only verified option mostly expires and the alternative is unconfirmed; there is time to confirm."),
    ("N01", n01_plain_order, "BUY:S4", "blind", "S4 is the cheapest verified supplier that arrives before stock runs out."),
    ("N02", n02_open_order_covers, "WAIT", "blind", "An acknowledged open order covers demand; nothing questions it."),
    ("N03", n03_conflicting_arrival, "REQUEST_INFO", "blind", "Two sources disagree on when the covering order arrives."),
    ("N04", n04_confirmed_on_schedule, "WAIT", "blind", "The only new fact confirms the order is on schedule."),
    ("N05", n05_irrelevant_tentative_note, "WAIT", "blind",
     "A tentative note about next quarter's price does not affect whether current supply is adequate."),
    ("N06", n06_harmful_delay, "EXPEDITE:PO-2001", "blind", "The delayed order causes a gap that expediting closes cheaply."),
    ("N07", n07_hold_might_be_released, "BUY:S4", "blind",
     "Stock on hold cannot be counted on a 'might be released'; order from a verified supplier."),
    ("N08", n08_expired_cheaper_quote, "BUY:S5", "blind",
     "S4's quote expired; S5 is the cheapest remaining verified supplier and still arrives before stock runs out."),
    ("N09", n09_supplier_not_sure, "REQUEST_INFO", "blind", "The supplier itself will not commit to the covering delivery."),
    ("N10", n10_budget_too_small, "ESCALATE", "blind", "Every compliant order exceeds the budget."),
]
