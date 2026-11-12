"""Extra tests for kernel/compress.py - coverage boost."""

import pytest

import kernel.compress as compress


def test_compress_code_full_path_guardrails_then_available_false(monkeypatch):
    # Long text with many def/class keywords -> guardrails skip
    long_text = "\n".join(f"def f{i}():\n    pass\n" for i in range(50))
    monkeypatch.setattr(compress, "available", lambda: True)
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert meta == {"skipped": "guardrails"}


def test_compress_code_available_but_model_none(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)
    monkeypatch.setattr(compress, "_get_model", lambda: None)
    # Text long enough to pass guardrails
    long_text = "x = 1\n" * 200
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert "skipped" in meta


def test_compress_code_compress_error(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)

    class FakeModel:
        def compress_prompt(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(compress, "_get_model", lambda: FakeModel())
    long_text = "x = 1\n" * 200
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert meta["skipped"] == "compress_error:RuntimeError"


def test_compress_code_empty_result(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)

    class FakeModel:
        def compress_prompt(self, *a, **k):
            return {"compressed_prompt": ""}

    monkeypatch.setattr(compress, "_get_model", lambda: FakeModel())
    long_text = "x = 1\n" * 200
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert meta == {"skipped": "empty_result"}


def test_compress_snippets_partial_compression(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)
    monkeypatch.setattr(compress, "_get_model", lambda: None)
    # First snippet short (guardrails skip), second long but model None -> skip
    out, meta = compress.compress_snippets(["x = 1\n", "y = 2\n" * 200])
    assert out == ["x = 1\n", "y = 2\n" * 200]
    assert meta["applied"] == 0


def test_maybe_log_with_orig_tokens(capsys):
    compress.maybe_log({"orig_tokens": 1000, "new_tokens": 500, "ratio": 0.5}, label="test")
    captured = capsys.readouterr()
    assert "[compress] test" in captured.out
