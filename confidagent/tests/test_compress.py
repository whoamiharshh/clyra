"""Tests for kernel/compress.py - prompt compression guardrails."""

import pytest

import kernel.compress as compress


def test_compress_code_preserve_list(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)
    text = "x = 1\n"
    out, meta = compress.compress_code(text, preserve=[text])
    assert out == text
    assert meta == {"skipped": "preserve_list"}


def test_compress_code_llmlingua_not_installed(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: False)
    text = "x = 1\n"
    out, meta = compress.compress_code(text)
    assert out == text
    assert meta == {"skipped": "llmlingua_not_installed"}


def test_compress_code_below_min_tokens(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)
    text = "x = 1\n"  # too short to compress
    out, meta = compress.compress_code(text)
    assert out == text
    assert meta == {"skipped": "guardrails"}


def test_compress_snippets_nothing_compressed(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: False)
    out, meta = compress.compress_snippets(["a", "b"])
    assert out == ["a", "b"]
    assert meta == {"applied": 0, "skipped": "nothing_compressed"}


def test_available_false_when_model_failed(monkeypatch):
    compress._model_failed = True
    try:
        assert compress.available() is False
    finally:
        compress._model_failed = False


def test_maybe_log_no_orig_tokens(capsys):
    compress.maybe_log({"applied": 0}, label="test")
    captured = capsys.readouterr()
    assert captured.out == ""
