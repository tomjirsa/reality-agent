import os
import pytest

def test_settings_defaults():
    from shared.config import Settings
    s = Settings(postgres_url="postgresql://localhost/test")
    assert s.scrape_interval_hours == 6
    assert s.bargain_score_threshold == 70.0
    assert s.hot_offer_max_days == 7
    assert s.smtp_port == 587

def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://localhost/test")
    monkeypatch.setenv("HOT_OFFER_MAX_DAYS", "14")
    monkeypatch.setenv("SCRAPE_INTERVAL_HOURS", "12")
    from importlib import reload
    import shared.config as cfg_module
    reload(cfg_module)
    assert cfg_module.settings.hot_offer_max_days == 14
    assert cfg_module.settings.scrape_interval_hours == 12
