"""Download the public M5 (Walmart) sales data and extract the small demand subset Nexus uses.

    python scripts/fetch_m5.py

Source: M5 Forecasting - Accuracy (Kaggle / Makridakis et al.), via the public Nixtla mirror.
The raw data is NOT committed to this repository; data/history/ and data/m5_cache/ are git-ignored.
Output: data/history/m5_subset.csv with columns date,item_id,units (4 California stores summed).
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = "https://raw.githubusercontent.com/Nixtla/m5-forecasts/main/datasets/m5.zip"
ITEMS = ["FOODS_3_090", "FOODS_3_288", "FOODS_3_586"]
DAYS = 56
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "m5_cache" / "m5.zip"
OUT = ROOT / "data" / "history" / "m5_subset.csv"


def main(zip_path: str | None = None):
    src = Path(zip_path) if zip_path else CACHE
    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL} (~50 MB) ...")
        urllib.request.urlretrieve(URL, src)
    with zipfile.ZipFile(src) as z:
        sales = pd.read_csv(io.BytesIO(z.read("sales_train_evaluation.csv")))
        cal = pd.read_csv(io.BytesIO(z.read("calendar.csv")))
    dcols = [c for c in sales.columns if c.startswith("d_")]
    last = dcols[-DAYS:]
    dates = {f"d_{i + 1}": d for i, d in enumerate(cal["date"])}  # calendar row i <-> d_(i+1)
    sub = sales[(sales.state_id == "CA") & (sales.item_id.isin(ITEMS))]
    agg = sub.groupby("item_id")[last].sum()
    rows = [{"date": dates[d], "item_id": it, "units": int(agg.loc[it, d])} for it in ITEMS for d in last]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(rows)} rows, {rows[0]['date']} .. {rows[-1]['date']})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
