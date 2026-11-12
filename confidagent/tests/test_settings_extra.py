"""Extra tests for kernel/settings.py - env override coverage."""

import os

from kernel.settings import AppSettings, _env_bool


def test_env_override_bifrost(monkeypatch):
    monkeypatch.setenv("BIFROST_BASE_URL", "http://custom:9999/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "custom-key")
    s = AppSettings()
    assert s.bifrost_base_url == "http://custom:9999/v1"
    assert s.bifrost_api_key == "custom-key"


def test_env_override_budget(monkeypatch):
    monkeypatch.setenv("CONFIDAGENT_BUDGET_USD", "5.50")
    s = AppSettings()
    assert s.budget_usd == 5.50


def test_env_override_model(monkeypatch):
    monkeypatch.setenv("MODEL_CHEAP", "custom-cheap")
    monkeypatch.setenv("MODEL_POWERFUL", "custom-powerful")
    monkeypatch.setenv("MODEL_LOCAL", "custom-local")
    s = AppSettings()
    assert s.model_cheap == "custom-cheap"
    assert s.model_powerful == "custom-powerful"
    assert s.model_local == "custom-local"


def test_env_override_cache_ttl(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "7200")
    s = AppSettings()
    assert s.cache_ttl_seconds == 7200


def test_env_bool_edge_cases():
    assert _env_bool("NOPE_XYZ", True) is True
    assert _env_bool("NOPE_XYZ", False) is False
