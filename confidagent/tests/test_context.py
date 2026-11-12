"""Tests for kernel/context.py - AST-based code context builder."""

import ast
import os
import tempfile

import pytest

from kernel.context import expand, file_outline, repo_map, symbol_body, tokens


def _write(tmp_path, name, source):
    p = os.path.join(tmp_path, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(source)
    return p


def test_repo_map_contains_all_top_level_defs(tmp_path):
    source = """
def alpha():
    pass

class Beta:
    def method(self):
        pass

async def gamma():
    pass
"""
    _write(tmp_path, "mod.py", source)
    out = repo_map(str(tmp_path))
    assert "def alpha()" in out
    assert "class Beta" in out
    assert "def gamma()" in out


def test_symbol_body_returns_exact_lines(tmp_path):
    source = "x = 1\n\ndef hello():\n    return 42\n\nclass Thing:\n    pass\n"
    p = _write(tmp_path, "mod.py", source)
    body = symbol_body(str(tmp_path), os.path.basename(p), "hello")
    lines = body.splitlines()
    assert "def hello():" in lines[0]
    assert "    return 42" in lines[1]


def test_expand_concatenates_symbol_bodies(tmp_path):
    source = "def one():\n    return 1\n\ndef two():\n    return 2\n"
    p = _write(tmp_path, "mod.py", source)
    out = expand(str(tmp_path), os.path.basename(p), ["one", "two"])
    assert ":: one ---" in out
    assert ":: two ---" in out
    assert "return 1" in out
    assert "return 2" in out


def test_tokens_monotonic(tmp_path):
    short = tokens("hello world")
    long = tokens("hello world this is a longer string")
    assert long >= short


def test_outline_warns_over_300_lines(tmp_path):
    lines = ["def f{}():\n    pass\n".format(i) for i in range(400)]
    source = "\n".join(lines)
    p = _write(tmp_path, "big.py", source)
    out = file_outline(str(tmp_path), os.path.basename(p))
    assert "WARNING" in out and "300" in out
