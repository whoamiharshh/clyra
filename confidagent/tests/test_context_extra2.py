"""Extra tests for kernel/context.py - coverage boost."""

import os
import tempfile

from kernel.context import _outline_for_source, symbol_body


def test_outline_for_source_syntax_error():
    out = _outline_for_source("def foo(:\n    pass\n")
    assert "syntax error" in out


def test_symbol_body_not_found(tmp_path):
    p = os.path.join(str(tmp_path), "mod.py")
    with open(p, "w") as f:
        f.write("x = 1\n")
    out = symbol_body(str(tmp_path), "mod.py", "nonexistent")
    assert "not found" in out


def test_symbol_body_dotted_method(tmp_path):
    source = "class MyClass:\n    def my_method(self):\n        return 1\n"
    p = os.path.join(str(tmp_path), "mod.py")
    with open(p, "w") as f:
        f.write(source)
    out = symbol_body(str(tmp_path), "mod.py", "MyClass.my_method")
    assert "def my_method" in out
