"""Historical demand loader (M5 / Walmart). Falls back to None when the subset is absent."""
from __future__ import annotations

import csv
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "history" / "m5_subset.csv"
M5_NOTE = ("M5 Forecasting (Walmart) daily unit sales, 4 California stores summed, end of the "
           "dataset split as 28 days of history (2016-04-11..2016-05-08) plus 14 days of held-out actual sales (2016-05-09..2016-05-22), converted to cases at an ASSUMED pack size. Observed sales can "
           "understate demand on stockout days.")


def available() -> bool:
    return HISTORY_FILE.exists()


def load_cases(item_id: str, units_per_case: int, days: int = 28) -> list[int] | None:
    """Last `days` of daily sales for an M5 item, in whole cases (oldest first)."""
    if not HISTORY_FILE.exists():
        return None
    with HISTORY_FILE.open() as f:
        rows = [r for r in csv.DictReader(f) if r["item_id"] == item_id]
    rows.sort(key=lambda r: r["date"])
    units = [int(r["units"]) for r in rows][-days:]
    if len(units) < 14:
        return None
    return [round(u / units_per_case) for u in units]


def load_split(item_id: str, units_per_case: int, hist_days: int = 28, actual_days: int = 14):
    """(history, actuals): the planner only ever sees `history`; `actuals` are the following
    days of real sales, used solely to score decisions after the fact."""
    full = load_cases(item_id, units_per_case, days=hist_days + actual_days)
    if not full or len(full) < hist_days + actual_days:
        return None
    return full[:hist_days], full[hist_days:]
