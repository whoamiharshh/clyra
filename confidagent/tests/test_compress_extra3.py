"""Extra tests for kernel/compress.py - available and _get_model paths."""

import kernel.compress as compress


def test_compress_code_llmlingua_installed_but_model_fails(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)
    monkeypatch.setattr(compress, "_get_model", lambda: None)
    long_text = "x = 1\n" * 200
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert meta == {"skipped": "llmlingua_not_installed"}


def test_compress_code_guardrails_then_available(monkeypatch):
    # Text with too many def/class keywords -> guardrails skip before available() is even relevant
    text = "\n".join(f"def f{i}():\n    pass\n" for i in range(50))
    monkeypatch.setattr(compress, "available", lambda: True)
    out, meta = compress.compress_code(text)
    assert out == text
    assert meta == {"skipped": "guardrails"}
