"""Document & Data Agent: NDI extraction with a clearly labeled local fallback.

Every fact keeps its source document ID, the exact excerpt it came from, and the
planning day on which Nexus learned it. Ship dates and arrival dates are separate fields.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from .config import get_settings

DAY0 = dt.date(2026, 11, 16)  # planning day 0 of the simulation
DOC_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"
CACHE_DIR = Path(__file__).resolve().parent.parent / "results" / "ndi_cache"


def date_to_day(s: str) -> int:
    return (dt.date.fromisoformat(s) - DAY0).days


def list_documents() -> list[Path]:
    return sorted(DOC_DIR.glob("*.txt"))


def doc_id(path: Path) -> str:
    return path.name.split("_")[0]


# ------------------------------------------------------------ NDI (live, via nace-sdk)
NDI_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": "string"},
        "unit_price_usd_per_case": {"type": "number"},
        "minimum_order_quantity_cases": {"type": "integer"},
        "order_multiple_cases": {"type": "integer"},
        "lead_time_days": {"type": "integer", "description": "Days from order to delivery at the customer DC"},
        "capacity_cases": {"type": "integer"},
        "capacity_is_confirmed": {"type": "boolean",
                                  "description": "true only if capacity is stated as confirmed; false if tentative"},
        "shelf_life_on_delivery_days": {"type": "integer"},
        "quote_valid_until": {"type": "string", "description": "ISO date YYYY-MM-DD"},
        "purchase_order_number": {"type": "string"},
        "new_ship_date": {"type": "string", "description": "ISO date the goods SHIP from the supplier (not arrival)"},
        "transit_days": {"type": "integer"},
    },
}
NDI_TO_FIELD = {"unit_price_usd_per_case": "unit_price", "minimum_order_quantity_cases": "moq",
                "order_multiple_cases": "pack_multiple", "lead_time_days": "lead_time_days",
                "capacity_cases": "capacity", "shelf_life_on_delivery_days": "shelf_life_days",
                "quote_valid_until": "valid_until", "purchase_order_number": "po",
                "new_ship_date": "new_ship_date", "transit_days": "transit_days"}


def ndi_extract(path: Path) -> dict | None:
    """NDI Extract (schema + citations) through the official nace-sdk when NACE_API_KEY is set.
    Cached by content hash. Returns {'data','fields',...} or {'error': ...}; None when NDI is off."""
    s = get_settings()
    if not s.ndi_live:
        return None
    data = path.read_bytes()
    key = hashlib.sha256(data + json.dumps(NDI_SCHEMA, sort_keys=True).encode()).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    try:
        from nace_sdk import NaceClient

        with NaceClient(api_key=s.nace_api_key) as client:
            up = client.documents.upload(path, on_conflict="new_version")
            job = client.documents.extract(up.as_source(), schema=NDI_SCHEMA, wait_seconds=60)
            if job.status != "succeeded":
                job = client.jobs.wait(job.job_id, timeout=120)
            out = json.loads(json.dumps(job.result, default=str))
        out["_job_id"] = str(job.job_id)
        cached.write_text(json.dumps(out, indent=2))
        return out
    except Exception as exc:  # surfaced in the UI, never hidden
        return {"error": f"NDI call failed: {type(exc).__name__}: {str(exc)[:300]}"}


def _merge_ndi(facts: list[dict], raw: dict, did: str, learned_day: int) -> list[dict]:
    """Prefer NDI values (with NDI citations) for single-supplier documents; keep local facts otherwise."""
    data = raw.get("data") or {}
    cites = {f.get("path"): f for f in (raw.get("fields") or []) if isinstance(f, dict)}
    by_field = {f["field"]: f for f in facts if f["field"] in NDI_TO_FIELD.values()}
    multi = len({f["supplier"] for f in facts if f.get("supplier")}) > 1
    for nk, fk in NDI_TO_FIELD.items():
        val = data.get(nk)
        if val is None or multi:
            continue
        c = cites.get(nk) or cites.get("$." + nk) or cites.get("/" + nk) or {}
        src = ((c.get("first_citation") or {}).get("source_text")) if isinstance(c.get("first_citation"), dict) else None
        f = by_field.get(fk)
        if f is None:
            f = {"source_id": did, "field": fk, "supplier": DOC_SUPPLIER.get(did), "status": "stated",
                 "learned_day": learned_day, "excerpt": src or ""}
            facts.append(f)
        if str(f.get("value")) != str(val) and f.get("value") is not None:
            f["local_value"] = f["value"]
        f["value"] = str(int(val)) if isinstance(val, float) and val.is_integer() and fk != "unit_price" else str(val)
        if src:
            f["excerpt"] = src
        f["extractor"] = "ndi-live"
        if c.get("confidence") is not None:
            f["ndi_confidence"] = c.get("confidence")
    if data.get("capacity_is_confirmed") is False and not multi and "capacity" in by_field:
        by_field["capacity"]["status"] = "tentative"
    return facts


# ------------------------------------------------------------ local fallback extractor
_PATTERNS = {
    "unit_price": r"\$(\d+(?:\.\d+)?)\s*(?:per|/)\s*case",
    "moq": r"(?:MOQ|Minimum order quantity)[:\s]+(\d+)",
    "pack_multiple": r"(?:Order multiple|multiples? of|multiple)[:\s]+(\d+)",
    "lead_time_days": r"(?:Lead time[:\s]+|in\s+)(\d+)\s*days",
    "capacity": r"(?:[Cc]apacity[^\d\n]*?|up to\s+)(\d+)\s*(?:cases|\()",
    "shelf_life_days": r"(?:shelf life[^\n\d]*?)(\d+)\s*days",
    "valid_until": r"[Vv]alid until[:\s]+(\d{4}-\d{2}-\d{2})",
    "po": r"PO[:\s]+(PO-\d+)",
    "new_ship_date": r"New ship date[:\s]+(\d{4}-\d{2}-\d{2})",
    "transit_days": r"Transit time[:\s]+(\d+)\s*days",
}
DOC_SUPPLIER = {"DOC-Q1": "S1", "DOC-Q2": "S2", "DOC-Q3": "S3", "DOC-D1": "S2"}
_TENTATIVE = re.compile(r"\b(probably|will confirm|need to check|tentative|estimate)\b", re.I)


def _excerpt(text: str, m: re.Match) -> str:
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    return text[start:end if end != -1 else None].strip()


def local_extract(path: Path, learned_day: int = 0) -> list[dict]:
    text = path.read_text()
    did = doc_id(path)
    facts = []
    # sourcing sheets list several suppliers, one per line
    lines = text.splitlines()
    for line in lines if "Supplier S" in text else [text]:
        sup = re.search(r"Supplier (S\d)", line)
        scope = line
        for field, pat in _PATTERNS.items():
            for m in re.finditer(pat, scope, re.I):
                ex = _excerpt(scope, m)
                facts.append({
                    "source_id": did, "field": field, "value": m.group(1), "excerpt": ex,
                    "supplier": sup.group(1) if sup else DOC_SUPPLIER.get(did),
                    "status": "tentative" if _TENTATIVE.search(ex) else
                    ("confirmed" if "confirmed" in ex.lower() else "stated"),
                    "learned_day": learned_day, "extractor": "local-fallback",
                })
                break
    _derive_arrival(facts, did, learned_day)
    return facts


def _derive_arrival(facts: list[dict], did: str, learned_day: int) -> None:
    """arrival = ship date + transit days (a ship date is never treated as an arrival date)."""
    ship = next((f for f in facts if f["field"] == "new_ship_date"), None)
    transit = next((f for f in facts if f["field"] == "transit_days"), None)
    if not (ship and transit):
        return
    try:
        arrival = date_to_day(str(ship["value"])[:10]) + int(float(transit["value"]))
    except ValueError:
        return
    facts[:] = [f for f in facts if f["field"] != "new_arrival_day"]
    facts.append({"source_id": did, "field": "new_arrival_day", "value": str(arrival),
                  "excerpt": f"{ship['excerpt']} + {transit['excerpt']}", "supplier": DOC_SUPPLIER.get(did),
                  "status": "derived", "learned_day": learned_day, "extractor": "nexus (ship date + transit)"})


def extract(path: Path, learned_day: int = 0) -> dict:
    """Returns {'facts': [...], 'ndi': raw-or-None, 'mode': 'ndi-live'|'local-fallback'}."""
    raw = ndi_extract(path)
    facts = local_extract(path, learned_day)
    mode = "ndi-live" if raw and "error" not in raw else "local-fallback"
    if mode == "ndi-live":
        facts = _merge_ndi(facts, raw, doc_id(path), learned_day)
        _derive_arrival(facts, doc_id(path), learned_day)
    return {"facts": facts, "ndi": raw, "mode": mode}


def apply_delay_notice(scn, facts: list[dict]) -> list[str]:
    """Event-triggered update: a delay notice moves an open order and marks it delayed."""
    changes = []
    po = next((f["value"] for f in facts if f["field"] == "po"), None)
    arr = next((f for f in facts if f["field"] == "new_arrival_day"), None)
    if not (po and arr):
        return changes
    for p in scn.products:
        for o in p.open_orders:
            if o.id == po:
                old = o.arrival_day
                o.arrival_day, o.status = int(arr["value"]), "delayed"
                changes.append(f"{po}: arrival day {old} -> {o.arrival_day} (source {arr['source_id']}: ship date + transit)")
    scn.facts.extend(facts)
    return changes
