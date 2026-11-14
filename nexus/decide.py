"""Decision providers with one interface: Drex (System 1), comparison LLM (System 2), offline rule baseline.

All providers receive the SAME state text and the SAME allowed action IDs, and must return
one of those IDs plus a reason code. Explanations are built from validated facts + reason code;
no chain-of-thought is requested or displayed.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field

import requests

from .config import get_settings
from .planning import Candidate

REASON_CODES = {
    "covers_demand_lowest_cost": "Meets projected demand at the lowest compliant cost.",
    "avoids_expiry_waste": "Avoids buying more than can be sold before expiry.",
    "unverified_commitment": "A key supplier commitment is tentative or unverified.",
    "conflicting_evidence": "Documents disagree on a fact the decision depends on.",
    "split_needed": "No single compliant supplier can cover demand.",
    "recover_delayed_order": "An existing order is delayed; recovering it is cheaper than a new order.",
    "existing_supply_sufficient": "Existing stock and open orders already cover demand.",
    "no_compliant_plan": "No compliant option meets demand within constraints.",
}

DECISION_INSTRUCTIONS = (
    "You are the procurement decision step of a supply-chain planner. Choose exactly one action. "
    "Priority: (1) never rely on tentative, unverified, expired or conflicting facts - request information "
    "instead when the best option depends on them; (2) minimize unmet demand; (3) minimize total cost "
    "including expected expiry waste; (4) do not order when existing supply covers demand; "
    "(5) escalate when no compliant option meets demand."
)


@dataclass
class DecisionResult:
    provider: str
    model: str
    live: bool
    action: str | None
    reason: str | None
    probabilities: dict = field(default_factory=dict)
    confidence: float | None = None
    latency_ms: float = 0.0
    model_ms: float | None = None  # server-side evaluation time when the API reports it
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    valid_output: bool = False
    error: str | None = None
    escalated: bool = False  # hybrid only: Drex was unsure and the LLM decided
    drex_confidence: float | None = None

    def to_dict(self):
        return asdict(self)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def build_state(header: dict, facts: list[dict], missing: list[str], conflicts: list[str]) -> str:
    lines = ["PLANNING STATE (simulated data)"]
    for k, v in header.items():
        lines.append(f"- {k}: {v}")
    if facts:
        lines.append("DOCUMENT FACTS (source id | field | value | status | excerpt):")
        for f in facts:
            lines.append(f"- {f['source_id']} | {f['field']} | {f['value']} | {f.get('status','stated')} | \"{f['excerpt']}\"")
    if missing:
        lines.append("MISSING INFORMATION: " + "; ".join(missing))
    if conflicts:
        lines.append("CONFLICTING INFORMATION: " + "; ".join(conflicts))
    return "\n".join(lines)


# ------------------------------------------------------------ Drex
class DrexProvider:
    name = "drex"

    def __init__(self):
        self.s = get_settings()

    @property
    def live(self):
        return self.s.drex_live

    def decide(self, state: str, options: list[Candidate]) -> DecisionResult:
        model = self.s.drex_model
        res = DecisionResult(provider=self.name, model=model, live=self.live, action=None, reason=None)
        if not self.live:
            res.error = "Drex not configured (set NACE_API_KEY in .env)"
            return res
        body = {
            "model": model,
            "state": state,
            "questions": {
                "action": {"type": "choice", "instructions": DECISION_INSTRUCTIONS,
                           "criteria": {c.id: c.describe() for c in options}},
                "reason": {"type": "choice", "instructions": "Which reason best justifies the chosen action?",
                           "criteria": REASON_CODES},
            },
        }
        payload = json.dumps(body)
        res.input_tokens = est_tokens(payload)
        headers = {"Authorization": f"Bearer {self.s.drex_key}", "Content-Type": "application/json",
                   "X-Nace-Client": "nexus-drexathon/1"}
        t0 = time.perf_counter()
        try:
            wait = 0.2  # sequential, paced calls; back off on 403/429/5xx and respect Retry-After
            for attempt in range(4):
                time.sleep(wait)
                t0 = time.perf_counter()
                r = requests.post(self.s.drex_url, data=payload, timeout=self.s.timeout_s, headers=headers)
                if r.status_code not in (403, 429, 500, 502, 503):
                    break
                try:
                    wait = min(60.0, float(r.headers.get("retry-after", "")))
                except ValueError:
                    wait = 30.0 if r.status_code in (403, 429) else 3.0
            res.latency_ms = (time.perf_counter() - t0) * 1000
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            ans = data.get("answers", {})
            a, rs = ans.get("action", {}), ans.get("reason", {})
            if a.get("type") == "choice":
                res.action, res.probabilities, res.confidence = a.get("choice"), a.get("probabilities", {}), a.get("confidence")
            if rs.get("type") == "choice":
                res.reason = rs.get("choice")
            usage = data.get("usage") or {}
            res.input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or res.input_tokens
            res.output_tokens = 0  # Drex bills input tokens only
            res.model = data.get("model") or model
            res.model_ms = data.get("evaluation_time_ms")
            res.valid_output = res.action in {c.id for c in options}
            if not res.valid_output:
                res.error = f"invalid or refused action: {a}"
        except Exception as exc:
            res.latency_ms = (time.perf_counter() - t0) * 1000
            res.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        res.cost_usd = res.input_tokens / 1e6 * self.s.drex_price_per_m_input
        return res


# ------------------------------------------------------------ System 2 LLM (DeepInfra, OpenAI-compatible)
class LLMProvider:
    name = "llm"

    def __init__(self):
        self.s = get_settings()

    @property
    def live(self):
        return self.s.llm_live

    def decide(self, state: str, options: list[Candidate]) -> DecisionResult:
        model = self.s.llm_model or "(SYSTEM2_MODEL not set)"
        res = DecisionResult(provider=self.name, model=model, live=self.live, action=None, reason=None)
        if not self.live:
            res.error = "System 2 LLM not configured (set DEEPINFRA_API_KEY and SYSTEM2_MODEL)"
            return res
        opts = "\n".join(f"- {c.id}: {c.describe()}" for c in options)
        reasons = "\n".join(f"- {k}: {v}" for k, v in REASON_CODES.items())
        prompt = (f"{DECISION_INSTRUCTIONS}\n\n{state}\n\nALLOWED ACTIONS:\n{opts}\n\nREASON CODES:\n{reasons}\n\n"
                  'Reply with ONLY a JSON object: {"action": "<one allowed action id>", "reason": "<one reason code>"}')
        body = {"model": model, "temperature": 0, "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]}
        t0 = time.perf_counter()
        try:
            r = requests.post(self.s.llm_url, json=body, timeout=self.s.timeout_s * 4, headers={
                "Authorization": f"Bearer {self.s.deepinfra_api_key}"})
            res.latency_ms = (time.perf_counter() - t0) * 1000
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            res.input_tokens = usage.get("prompt_tokens") or est_tokens(prompt)
            res.output_tokens = usage.get("completion_tokens") or est_tokens(text)
            m = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(m.group(0)) if m else {}
            res.action, res.reason = parsed.get("action"), parsed.get("reason")
            res.valid_output = res.action in {c.id for c in options}
            if not res.valid_output:
                res.error = f"invalid action in output: {text[:200]}"
        except Exception as exc:
            res.latency_ms = (time.perf_counter() - t0) * 1000
            res.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        res.cost_usd = (res.input_tokens / 1e6 * self.s.llm_price_per_m_input
                        + res.output_tokens / 1e6 * self.s.llm_price_per_m_output)
        return res


# ------------------------------------------------------------ Offline rule baseline (no model)
class RuleBaseline:
    """Transparent replenishment policy used offline and as a benchmark baseline.
    Picks the cheapest hard-valid order with no unmet demand and no warnings."""
    name = "rule-baseline"
    live = False

    def decide(self, state: str, options: list[Candidate]) -> DecisionResult:
        t0 = time.perf_counter()
        orders = [c for c in options if c.kind in ("BUY", "SPLIT", "EXPEDITE")]
        clean = [c for c in orders if c.unmet < 1 and not c.warnings]
        wait = next(c for c in options if c.kind == "WAIT")
        if wait.unmet < 1 and not orders:
            action, reason = "WAIT", "existing_supply_sufficient"
        elif clean:
            best = min(clean, key=lambda c: c.cost)
            action = best.id
            reason = {"SPLIT": "split_needed", "EXPEDITE": "recover_delayed_order"}.get(best.kind, "covers_demand_lowest_cost")
        elif any(c.unmet < 1 for c in orders):
            action, reason = "REQUEST_INFO", "unverified_commitment"
        else:
            action, reason = "ESCALATE", "no_compliant_plan"
        return DecisionResult(provider=self.name, model="deterministic rules", live=False, action=action,
                              reason=reason, latency_ms=(time.perf_counter() - t0) * 1000, valid_output=True)


# ------------------------------------------------------------ Hybrid: Drex first, LLM only when Drex is unsure
class HybridProvider:
    """Drex decides. If its confidence in the chosen action is below HYBRID_THRESHOLD (or its output
    is invalid), the same question goes to the System 2 LLM. Latency and cost are summed."""
    name = "hybrid"

    def __init__(self):
        import os
        self.drex, self.llm = DrexProvider(), LLMProvider()
        self.threshold = float(os.environ.get("HYBRID_THRESHOLD") or 0.6)

    @property
    def live(self):
        return self.drex.live and self.llm.live

    def decide(self, state: str, options: list[Candidate]) -> DecisionResult:
        d = self.drex.decide(state, options)
        unsure = (not d.valid_output) or d.confidence is None or d.confidence < self.threshold
        if not unsure or not self.llm.live:
            d.provider, d.drex_confidence = self.name, d.confidence
            return d
        l = self.llm.decide(state, options)
        l.provider, l.model = self.name, f"{d.model} -> {l.model}"
        l.escalated, l.drex_confidence = True, d.confidence
        l.latency_ms += d.latency_ms
        l.cost_usd += d.cost_usd
        l.input_tokens += d.input_tokens
        l.probabilities = d.probabilities
        return l


def get_provider(name: str):
    return {"drex": DrexProvider, "llm": LLMProvider, "hybrid": HybridProvider,
            "rule-baseline": RuleBaseline}[name]()
