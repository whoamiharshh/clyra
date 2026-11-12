"""Extra tests for kernel/compress.py - coverage boost."""

import kernel.compress as compress


def test_passes_guardrails_short():
    assert compress._passes_guardrails("x = 1\n") is False


def test_passes_guardrails_too_many_keywords():
    text = "\n".join(f"def f{i}():\n    pass\n" for i in range(50))
    assert compress._passes_guardrails(text) is False


def test_passes_guardrails_ok():
    text = "x = 1 + 2\n" * 100
    assert compress._passes_guardrails(text) is True


def test_compress_code_skipped_compress_error(monkeypatch):
    monkeypatch.setattr(compress, "available", lambda: True)

    class FakeModel:
        def compress_prompt(self, *a, **k):
            raise ValueError("test error")

    monkeypatch.setattr(compress, "_get_model", lambda: FakeModel())
    long_text = "x = 1\n" * 200
    out, meta = compress.compress_code(long_text)
    assert out == long_text
    assert meta["skipped"] == "compress_error:ValueError"
