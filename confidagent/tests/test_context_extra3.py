"""Extra tests for kernel/context.py - tokens, _unparse_args, find_symbol_line_range."""

import os
import tempfile

import pytest

from kernel import context as ctx


def test_tokens_fallback_path(monkeypatch):
    monkeypatch.setattr(ctx, "_tiktoken_failed", True)
    monkeypatch.setattr(ctx, "_cl100k_encoder", None)
    assert ctx.tokens("hello world") == len("hello world") // 4
    assert ctx.tokens("") == 0


def test_tokens_tiktoken_import_fails(monkeypatch):
    monkeypatch.setattr(ctx, "_tiktoken_failed", False)
    monkeypatch.setattr(ctx, "_cl100k_encoder", None)

    def fake_import(name):
        if name == "tiktoken":
            raise ImportError("no tiktoken")
        raise ImportError(name)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = ctx.tokens("hello world")
    assert result == len("hello world") // 4
    assert ctx._tiktoken_failed is True


def test_unparse_args_with_annotation():
    import ast
    source = "def f(x: int, y: str = 'hi') -> bool:\n    pass\n"
    tree = ast.parse(source)
    func = tree.body[0]
    result = ctx._unparse_args(func.args)
    assert "x:int" in result
    assert "y:str" in result


def test_unparse_args_with_vararg():
    import ast
    source = "def f(*args, **kwargs):\n    pass\n"
    tree = ast.parse(source)
    func = tree.body[0]
    result = ctx._unparse_args(func.args)
    assert "*args" in result
    assert "**kwargs" in result


def test_find_symbol_line_range_not_found(tmp_path):
    p = os.path.join(str(tmp_path), "mod.py")
    with open(p, "w") as f:
        f.write("x = 1\n")
    result = ctx.find_symbol_line_range(str(tmp_path), "mod.py", "nonexistent")
    assert result is None


def test_sig_line_non_function_class():
    import ast
    tree = ast.parse("x = 1\n")
    node = tree.body[0]  # Assign, not FunctionDef/ClassDef
    result = ctx._sig_line(node)
    assert result == ""


def test_module_first_docstring_line():
    import ast
    tree = ast.parse('"""Module docstring."""\nx = 1\n')
    result = ctx._module_first_docstring_line(tree)
    assert '"""Module docstring.' in result


def test_unparse_args_posonly():
    import ast
    source = "def f(a, /, b):\n    pass\n"
    tree = ast.parse(source)
    func = tree.body[0]
    result = ctx._unparse_args(func.args)
    assert "a" in result and "b" in result
