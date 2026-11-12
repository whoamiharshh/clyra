"""Tests for kernel/gateway.py - LLM gateway with privacy enforcement."""

import os
import tempfile

import pytest
from openai import OpenAI

from kernel.gateway import Gateway, PrivateModeViolation


def test_tier_mapping(monkeypatch):
    """Gateway.complete routes cheap/powerful/local to the right settings model."""
    import importlib
    ks_module = importlib.import_module("kernel.settings")
    calls = []

    class FakeResponse:
        class Choice:
            message = type("m", (), {"content": "ok"})()

        choices = [Choice()]
        usage = type("u", (), {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})()
        model = "m"
        headers = {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs.get("model"))
                    return FakeResponse()

            completions = Completions()

        chat = Chat()

    monkeypatch.setattr(ks_module.settings, "model_cheap", "cheap-model")
    monkeypatch.setattr(ks_module.settings, "model_powerful", "powerful-model")
    monkeypatch.setattr(ks_module.settings, "model_local", "local-model")
    monkeypatch.setattr("kernel.gateway.make_openai_client", lambda *a, **k: FakeClient())
    # Disable confidential enforcement
    import security.privacy_checker as pc
    monkeypatch.setattr(pc, "enforce_local", lambda repo_path=None: False)

    gw = Gateway()
    gw.complete([{"role": "user", "content": "hi"}], tier="cheap")
    gw.complete([{"role": "user", "content": "hi"}], tier="powerful")
    gw.complete([{"role": "user", "content": "hi"}], tier="local")
    assert calls == ["cheap-model", "powerful-model", "local-model"]


def test_local_raises_when_ollama_down(monkeypatch):
    """Local tier must raise when Ollama is unreachable, never fall back to cloud."""
    calls = []

    class FakeClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    calls.append("called")
                    from openai import APIConnectionError
                    raise APIConnectionError("boom", request=None)

            completions = Completions()

        chat = Chat()

    import security.privacy_checker as pc
    monkeypatch.setattr(pc, "enforce_local", lambda repo_path=None: False)
    monkeypatch.setattr("kernel.gateway.make_openai_client", lambda *a, **k: FakeClient())

    gw = Gateway()
    with pytest.raises(Exception):
        gw.complete([{"role": "user", "content": "hi"}], tier="local")
    # Ollama was attempted (local route), cloud was not.
    assert len(calls) == 1


def test_private_mode_blocks_cloud_before_call(tmp_path, monkeypatch):
    """Confidential mode raises PrivateModeViolation before any network call."""
    # .confidential must be a file marker, not a directory
    open(os.path.join(str(tmp_path), ".confidential"), "w").close()
    called = []

    class FakeClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    called.append(True)
                    raise AssertionError("must not call cloud")

            completions = Completions()

        chat = Chat()

    import security.privacy_checker as pc
    monkeypatch.setattr(pc, "enforce_local", lambda repo_path=None: True)
    monkeypatch.setattr("kernel.gateway.make_openai_client", lambda *a, **k: FakeClient())

    gw = Gateway()
    with pytest.raises(PrivateModeViolation):
        gw.complete([{"role": "user", "content": "hi"}], tier="cheap")
    assert called == []
