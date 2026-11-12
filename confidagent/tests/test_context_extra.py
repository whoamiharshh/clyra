"""Extra tests for kernel/context.py - coverage boost."""

import os
import tempfile

import pytest

from kernel.context import _map_cap, tokens, expand, file_outline, repo_map, symbol_body


def test_map_cap_truncates():
    lines = [f"line {i}" for i in range(100)]
    out = _map_cap(lines, max_symbols=10)
    assert "90 more symbols" in out
    assert out.count("\n") == 10


def test_map_cap_no_truncate_when_short():
    lines = ["a", "b", "c"]
    out = _map_cap(lines, max_symbols=10)
    assert out == "a\nb\nc"


def test_tokens_fallback_monotonic():
    # tokens() should be monotonic even without tiktoken
    assert tokens("a b c") <= tokens("a b c d e f g h i j")


def test_tokens_empty():
    assert tokens("") == 0


def test_symbol_body_with_decorators(tmp_path):
    source = "@decorator\ndef decorated():\n    pass\n"
    p = os.path.join(str(tmp_path), "mod.py")
    with open(p, "w") as f:
        f.write(source)
    body = symbol_body(str(tmp_path), "mod.py", "decorated")
    assert "@decorator" in body
    assert "def decorated():" in body


def test_expand_empty_symbols(tmp_path):
    p = os.path.join(str(tmp_path), "mod.py")
    with open(p, "w") as f:
        f.write("x = 1\n")
    out = expand(str(tmp_path), "mod.py", [])
    assert out == ""
