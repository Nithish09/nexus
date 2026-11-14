"""Scenario: HISTORICAL demand (M5 / Walmart) when available, SIMULATED everything else.

Nothing here is a real supplier, price or inventory record. Demand history comes from
nexus.history (M5 subset) when data/history/m5_subset.csv exists, otherwise it is seeded
synthetic. Product names are illustrative labels for anonymized M5 items; supplier terms,
inventory, lead times and expiry are always simulated.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from . import history

PLANNING_HORIZON_DAYS = 14
SIMULATED_LABEL = "SIMULATED"


@dataclass
class Supplier:
    id: str
    name: str
    price_per_case: float  # USD
    lead_time_days: int  # order -> arrival at DC (incl. transit + receiving)
    moq_cases: int
    pack_multiple: int
    capacity_cases: int  # max cases available in this order window
    capacity_confirmed: bool
    quote_valid_until_day: int  # last planning day the quote is valid
    shelf_life_on_arrival_days: int
    approved: bool = True
    source_ids: list[str] = field(default_factory=list)


@dataclass
class OpenOrder:
    id: str
    supplier_id: str
    qty_cases: int
    arrival_day: int
    status: str = "ordered"  # ordered|acknowledged|shipped|delayed


@dataclass
class Product:
    id: str
    name: str
    unit: str
    on_hand: int
    reserved: int
    quality_hold: int
    safety_stock: int
    min_shelf_life_at_receipt_days: int
    suppliers: list[Supplier]
    open_orders: list[OpenOrder] = field(default_factory=list)
    demand_history: list[int] = field(default_factory=list)  # last 28 days, oldest first
    demand_source: str = "synthetic (seeded)"
    actual_demand: list[int] = field(default_factory=list)  # next 14 days; NEVER shown to the planner/model

    @property
    def available(self) -> int:
        """Usable stock: reservations and quality holds are NOT available."""
        return max(0, self.on_hand - self.reserved - self.quality_hold)

    def supplier(self, sid: str) -> Supplier:
        return next(s for s in self.suppliers if s.id == sid)


@dataclass
class Scenario:
    planning_day: int
    location: str
    budget_usd: float
    products: list[Product]
    storage_capacity_cases: int = 1500  # per product at this DC (simulated)
    facts: list[dict] = field(default_factory=list)  # extracted document facts
    missing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    label: str = SIMULATED_LABEL

    def product(self, pid: str) -> Product:
        return next(p for p in self.products if p.id == pid)

    def clone(self) -> "Scenario":
        return copy.deepcopy(self)


def synthetic_history(base: int, seed: int, days: int = 28) -> list[int]:
    """Weekly-seasonal synthetic daily demand (cases). Seeded and reproducible."""
    rng = random.Random(seed)
    weekly = [1.0, 0.9, 0.95, 1.0, 1.2, 1.4, 1.25]
    return [max(0, round(base * weekly[d % 7] + rng.gauss(0, base * 0.08))) for d in range(days)]


# Catalog product -> (M5 item used as its demand series, assumed units per case, synthetic fallback base)
DEMAND_SERIES = {"P1": ("FOODS_3_090", 6, 40), "P1-slow": ("FOODS_3_288", 6, 15), "P2": ("FOODS_3_586", 8, 18)}


def demand_for(key: str, seed: int = 7, holdout: bool = False) -> tuple[list[int], str, list[int]]:
    """(history, source label, actuals). Historical M5 when data/history/m5_subset.csv exists, else synthetic.

    holdout=False: history = the latest 28 days, no actuals (nothing after them exists).
    holdout=True : history = the 28 days ending 14 days earlier; actuals = the real 14 days that followed,
                   used only to score decisions after the fact."""
    item, per_case, base = DEMAND_SERIES[key]
    label = f"HISTORICAL: M5 item {item}, 4 CA stores summed, {per_case} units/case (assumed)"
    if holdout:
        split = history.load_split(item, per_case)
        if split:
            return split[0], label + ", 14 following days held out for scoring", split[1]
        full = synthetic_history(base, seed, days=42)
        return full[:28], "SYNTHETIC (seeded) - run scripts/fetch_m5.py for historical demand", full[28:]
    hist = history.load_cases(item, per_case)
    if hist:
        return hist, label, []
    return synthetic_history(base, seed), "SYNTHETIC (seeded) - run scripts/fetch_m5.py for historical demand", []


def base_scenario(seed: int = 7) -> Scenario:
    d1, src1, a1 = demand_for("P1", seed)
    d2, src2, a2 = demand_for("P2", seed + 1)
    oat = Product(
        id="P1",
        name="Oat milk 1L",
        unit="case (6)",
        on_hand=260,
        reserved=40,
        quality_hold=0,
        safety_stock=60,
        min_shelf_life_at_receipt_days=14,
        demand_history=d1,
        demand_source=src1,
        actual_demand=a1,
        suppliers=[
            Supplier("S1", "Valley Oats Co.", 18.40, 3, 120, 24, 400, True, 10, 30, source_ids=["DOC-Q1"]),
            Supplier("S2", "Northfield Dairy Alt", 17.10, 6, 600, 50, 1200, True, 10, 25, source_ids=["DOC-Q2"]),
            Supplier("S3", "QuickShip Foods", 19.90, 2, 48, 12, 300, False, 10, 28, source_ids=["DOC-Q3"]),
        ],
    )
    brew = Product(
        id="P2",
        name="Cold brew 12oz",
        unit="case (8)",
        on_hand=150,
        reserved=10,
        quality_hold=20,
        safety_stock=30,
        min_shelf_life_at_receipt_days=30,
        demand_history=d2,
        demand_source=src2,
        actual_demand=a2,
        suppliers=[
            Supplier("S4", "Bean & Barrel", 31.00, 4, 60, 20, 300, True, 12, 90, source_ids=["DOC-Q4"]),
            Supplier("S5", "Coastline Beverage", 29.50, 7, 100, 25, 500, True, 12, 120, source_ids=["DOC-Q4"]),
            Supplier("S6", "Metro Distributors", 33.80, 2, 20, 10, 150, True, 5, 75, source_ids=["DOC-Q4"]),
        ],
    )
    return Scenario(planning_day=0, location="DC-SF", budget_usd=20000.0, products=[oat, brew])


DOC_PRODUCT = {"DOC-Q1": "P1", "DOC-Q2": "P1", "DOC-Q3": "P1", "DOC-Q4": "P2", "DOC-D1": "P1"}


def demo_scenario(seed: int = 7) -> Scenario:
    """Demo: oat milk is covered by open PO-1001 (S2) until a delay notice arrives."""
    scn = base_scenario(seed)
    p1 = scn.product("P1")
    p1.on_hand = 380
    p1.open_orders = [OpenOrder("PO-1001", "S2", 600, 5, "acknowledged")]
    return scn
