"""Runtime configuration. Secrets come only from environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional
    from dotenv import load_dotenv

    load_dotenv(override=True)  # .env always wins over stale shell exports
except Exception:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Settings:
    nace_api_key: str | None
    deepinfra_api_key: str | None
    # Drex decisions endpoint. Two supported routes:
    #  1) Nace console endpoint (set DREX_URL + NACE_API_KEY)
    #  2) DeepInfra-hosted Drex: https://api.deepinfra.com/v1/decisions (DEEPINFRA_API_KEY)
    drex_url: str
    drex_model: str
    drex_price_per_m_input: float
    # System 2 / comparison LLM (DeepInfra OpenAI-compatible). Model ID must come from organizer.
    llm_url: str
    llm_model: str | None
    llm_price_per_m_input: float
    llm_price_per_m_output: float
    # NDI runs through the nace-sdk whenever NACE_API_KEY is set; NDI_URL=off disables it
    ndi_url: str | None
    timeout_s: float

    @property
    def drex_key(self) -> str | None:
        if "deepinfra.com" in self.drex_url:
            return self.deepinfra_api_key
        return self.nace_api_key

    @property
    def drex_live(self) -> bool:
        return bool(self.drex_key and self.drex_url and self.drex_model)

    @property
    def llm_live(self) -> bool:
        return bool(self.deepinfra_api_key and self.llm_model)

    @property
    def ndi_live(self) -> bool:
        return bool(self.nace_api_key) and (self.ndi_url or "on").lower() != "off"


def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        nace_api_key=e("NACE_API_KEY") or None,
        deepinfra_api_key=e("DEEPINFRA_API_KEY") or None,
        drex_url=e("DREX_URL", "https://console.nace.ai/v1/systemone"),
        drex_model=e("DREX_MODEL", "drex-max-v1.1"),
        drex_price_per_m_input=float(e("DREX_PRICE_PER_M_INPUT") or 0),
        llm_url=e("SYSTEM2_URL", "https://api.deepinfra.com/v1/openai/chat/completions"),
        llm_model=e("SYSTEM2_MODEL") or None,
        llm_price_per_m_input=float(e("SYSTEM2_PRICE_PER_M_INPUT") or 0),
        llm_price_per_m_output=float(e("SYSTEM2_PRICE_PER_M_OUTPUT") or 0),
        ndi_url=e("NDI_URL") or None,
        timeout_s=float(e("API_TIMEOUT_S", "30")),
    )
