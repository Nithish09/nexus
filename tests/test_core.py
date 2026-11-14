import json

import pytest

from nexus import decide
from nexus.cases import CASES, c01_normal, c11_duplicate_run
from nexus.decide import DrexProvider, LLMProvider, RuleBaseline
from nexus.documents import apply_delay_notice, doc_id, extract, list_documents
from nexus.planner import plan_product, record
from nexus.planning import Candidate, generate_candidates, project, round_qty, validate
from nexus.scenario import OpenOrder, demo_scenario


def test_inventory_conservation():
    scn = demo_scenario()
    p = scn.product("P1")
    proj = project(p)
    start = p.available
    receipts = sum(r["receipts"] for r in proj["rows"])
    fulfilled = sum(r["fulfilled"] for r in proj["rows"])
    assert abs(start + receipts - fulfilled - proj["ending"]) < 1e-6
    assert all(r["end"] >= 0 for r in proj["rows"])


def test_reservations_and_holds_not_available():
    scn = demo_scenario()
    p = scn.product("P2")
    assert p.available == p.on_hand - p.reserved - p.quality_hold


def test_moq_and_pack_rounding():
    assert round_qty(130, 120, 24) == 144
    assert round_qty(10, 120, 24) == 120
    assert round_qty(127, 48, 12) == 132


def test_validator_rejects_expired_quote_and_capacity():
    scn = c01_normal()
    p = scn.products[0]
    p.supplier("S1").quote_valid_until_day = -1
    c = next(c for c in generate_candidates(scn, p) if c.id == "BUY:S1")
    assert any("quote expired" in v for v in c.violations)
    bad = Candidate(id="BUY:S1", kind="BUY", lines=[{"supplier_id": "S1", "qty": 1000, "arrival_day": 3,
                                                     "unit_price": 18.4}])
    validate(scn, p, bad)
    assert any("capacity" in v for v in bad.violations)


def test_duplicate_order_rejected():
    scn = c11_duplicate_run()
    p = scn.products[0]
    dup = Candidate(id="BUY:S1", kind="BUY", lines=[{"supplier_id": "S1", "qty": 192, "arrival_day": 3,
                                                     "unit_price": 18.4}])
    validate(scn, p, dup)
    assert any("duplicate" in v for v in dup.violations)


def test_invalid_model_output_never_overrides_validation():
    class Rogue:
        name, live = "rogue", True

        def decide(self, state, options):
            return decide.DecisionResult("rogue", "x", True, action="BUY:S3", reason=None, valid_output=True)

    scn = CASES[9][1]()  # insufficient budget: BUY:S3 violates budget
    plan = plan_product(scn, scn.products[0], Rogue())
    assert plan.final_action == "ESCALATE"
    assert plan.verification[0].startswith("REJECTED")


def test_ship_date_is_not_arrival_date():
    path = next(p for p in list_documents() if doc_id(p) == "DOC-D1")
    facts = extract(path)["facts"]
    arr = next(f for f in facts if f["field"] == "new_arrival_day")
    assert arr["value"] == "11"  # ship day 8 + 3 days transit
    scn = demo_scenario()
    apply_delay_notice(scn, facts)
    o = scn.product("P1").open_orders[0]
    assert (o.arrival_day, o.status) == (11, "delayed")


def test_tentative_capacity_flagged():
    path = next(p for p in list_documents() if doc_id(p) == "DOC-Q3")
    cap = next(f for f in extract(path)["facts"] if f["field"] == "capacity")
    assert cap["status"] == "tentative"


def test_idempotent_execution(tmp_path, monkeypatch):
    from nexus import planner
    monkeypatch.setattr(planner, "DB_PATH", tmp_path / "t.db")
    scn = demo_scenario()
    plan = plan_product(scn, scn.product("P2"), RuleBaseline())
    k1, new1 = record(plan, 0)
    k2, new2 = record(plan, 0)
    assert k1 == k2 and new1 and not new2


def test_rule_baseline_runs_all_cases():
    for cid, build, expected, split, why in CASES:
        scn = build()
        plan = plan_product(scn, scn.products[0], RuleBaseline())
        assert plan.final_action in {c.id for c in plan.candidates}


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_drex_request_and_parse(monkeypatch):
    monkeypatch.setenv("NACE_API_KEY", "test")
    monkeypatch.setenv("NDI_URL", "off")
    seen = {}

    def fake_post(url, data=None, json=None, timeout=None, headers=None):
        seen["body"] = __import__("json").loads(data)
        return _Resp({"answers": {"action": {"type": "choice", "choice": "BUY:S1", "confidence": 0.9,
                                             "probabilities": {"BUY:S1": 0.9, "WAIT": 0.1}},
                                  "reason": {"type": "choice", "choice": "covers_demand_lowest_cost"}},
                      "usage": {"input_tokens": 700, "output_tokens": 9}, "evaluation_time_ms": 130.0,
                      "model": "drex-max-v1.1"})

    monkeypatch.setattr(decide.requests, "post", fake_post)
    scn = c01_normal()
    plan = plan_product(scn, scn.products[0], DrexProvider())
    q = seen["body"]["questions"]["action"]
    assert q["type"] == "choice" and "BUY:S1" in q["criteria"] and "BUY:S3" in q["criteria"]
    assert plan.final_action == "BUY:S1" and plan.decision.valid_output
    assert plan.decision.input_tokens == 700 and plan.decision.model_ms == 130.0


def test_llm_request_and_parse(monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test")
    monkeypatch.setenv("SYSTEM2_MODEL", "some/model")
    monkeypatch.setattr(decide.requests, "post", lambda *a, **k: _Resp(
        {"choices": [{"message": {"content": '{"action": "WAIT", "reason": "existing_supply_sufficient"}'}}],
         "usage": {"prompt_tokens": 900, "completion_tokens": 20}}))
    scn = c11_duplicate_run()
    plan = plan_product(scn, scn.products[0], LLMProvider())
    assert plan.final_action == "WAIT" and plan.decision.input_tokens == 900


def test_history_loader_converts_units_to_cases(tmp_path, monkeypatch):
    from nexus import history
    f = tmp_path / "m5_subset.csv"
    rows = ["date,item_id,units"] + [f"2016-05-{d:02d},FOODS_3_090,{120 + d}" for d in range(1, 23)]
    f.write_text("\n".join(rows))
    monkeypatch.setattr(history, "HISTORY_FILE", f)
    cases = history.load_cases("FOODS_3_090", 6)
    assert len(cases) == 22 and cases[0] == round(121 / 6) and cases[-1] == round(142 / 6)
    assert history.load_cases("NOPE", 6) is None


def test_benchmark_expectations_hold_for_rule_checkable_cases():
    # the transparent baseline solves every case except the three that need judgment about evidence or necessity
    for cid, build, expected, split, why in CASES:
        scn = build()
        got = plan_product(scn, scn.products[0], RuleBaseline()).final_action
        assert (got == expected) or cid in ("C06", "C15", "C16"), (cid, got, expected)


def test_ndi_merge_prefers_ndi_values_and_keeps_ship_vs_arrival():
    from nexus import documents
    path = next(p for p in list_documents() if doc_id(p) == "DOC-D1")
    facts = documents.local_extract(path)
    raw = {"data": {"purchase_order_number": "PO-1001", "new_ship_date": "2026-11-24", "transit_days": 4},
           "fields": [{"path": "transit_days", "status": "found", "confidence": 0.9,
                       "first_citation": {"source_text": "Transit time: 4 days"}}]}
    merged = documents._merge_ndi(facts, raw, "DOC-D1", 0)
    documents._derive_arrival(merged, "DOC-D1", 0)
    t = next(f for f in merged if f["field"] == "transit_days")
    assert t["value"] == "4" and t["extractor"] == "ndi-live" and t["local_value"] == "3"
    assert next(f for f in merged if f["field"] == "new_arrival_day")["value"] == "12"


def test_hybrid_escalates_only_when_drex_is_unsure(monkeypatch):
    from nexus.decide import HybridProvider
    monkeypatch.setenv("NACE_API_KEY", "t")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "t")
    monkeypatch.setenv("SYSTEM2_MODEL", "some/model")
    conf = {"v": 0.4}

    def fake_post(url, data=None, json=None, timeout=None, headers=None):
        if "systemone" in url:
            return _Resp({"answers": {"action": {"type": "choice", "choice": "REQUEST_INFO", "confidence": conf["v"],
                                                 "probabilities": {}}, "reason": {"type": "choice", "choice": "x"}},
                          "usage": {"input_tokens": 500}})
        return _Resp({"choices": [{"message": {"content": '{"action": "WAIT", "reason": "existing_supply_sufficient"}'}}],
                      "usage": {"prompt_tokens": 900, "completion_tokens": 20}})

    monkeypatch.setattr(decide.requests, "post", fake_post)
    scn = c11_duplicate_run()
    low = plan_product(scn, scn.products[0], HybridProvider())
    assert low.decision.escalated and low.final_action == "WAIT" and low.decision.input_tokens == 1400
    conf["v"] = 0.95
    high = plan_product(scn, scn.products[0], HybridProvider())
    assert not high.decision.escalated and high.final_action == "REQUEST_INFO"


def test_storage_capacity_is_a_hard_constraint():
    from nexus.cases import c13_storage_limit
    scn = c13_storage_limit()
    c = next(c for c in generate_candidates(scn, scn.products[0]) if c.id == "BUY:S2")
    assert any("storage capacity" in v for v in c.violations)


def test_outcome_uses_actuals_and_conserves_inventory():
    from nexus.cases import c17_expedite_not_enough
    from nexus.planning import simulate_outcome
    scn = c17_expedite_not_enough()
    p = scn.products[0]
    assert len(p.actual_demand) == 14 and len(p.demand_history) == 28
    cands = {c.id: c for c in generate_candidates(scn, p)}
    wait, buy = simulate_outcome(p, cands["WAIT"]), simulate_outcome(p, cands["BUY:S1"])
    assert buy["unmet_cases"] <= wait["unmet_cases"] and 0 <= wait["fill_rate"] <= 1
    exp = simulate_outcome(p, cands["EXPEDITE:PO-1001"])
    # same total receipts in the horizon: every extra case sold comes out of ending inventory
    assert exp["ending_inventory"] == wait["ending_inventory"] - (wait["unmet_cases"] - exp["unmet_cases"])
