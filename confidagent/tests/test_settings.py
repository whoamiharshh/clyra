"""Tests for kernel/settings.py - FeatureFlags and env overrides."""

import os

import pytest

from kernel.settings import AppSettings, FeatureFlags, _env_bool, reload, settings


def test_feature_flags_defaults_all_true():
    ff = FeatureFlags()
    assert ff.ast_context is True
    assert ff.file_memory is True
    assert ff.routing is True
    assert ff.cache is True
    assert ff.cost_model is True
    assert ff.tool_minimization is True


def test_env_bool_true_values():
    for v in ("1", "true", "True", "yes", "on"):
        os.environ["TEST_ENV_BOOL"] = v
        try:
            assert _env_bool("TEST_ENV_BOOL", False) is True
        finally:
            del os.environ["TEST_ENV_BOOL"]


def test_env_bool_false_values():
    for v in ("0", "false", "no", "off", ""):
        os.environ["TEST_ENV_BOOL"] = v
        try:
            assert _env_bool("TEST_ENV_BOOL", True) is False
        finally:
            del os.environ["TEST_ENV_BOOL"]


def test_env_bool_missing_returns_default():
    assert _env_bool("DOES_NOT_EXIST_XYZ", False) is False
    assert _env_bool("DOES_NOT_EXIST_XYZ", True) is True


def test_settings_has_feature_flags():
    assert isinstance(settings.feature_flags, FeatureFlags)


def test_reload_returns_settings():
    s = reload()
    assert isinstance(s, AppSettings)
