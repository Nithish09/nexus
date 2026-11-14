import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never call live APIs, even when a real .env is present."""
    for k in ("NACE_API_KEY", "DEEPINFRA_API_KEY", "SYSTEM2_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NDI_URL", "off")
