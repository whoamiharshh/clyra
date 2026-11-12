import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from kernel.gateway import Gateway, PrivateModeViolation


def test_private_project_enforces_local(tmp_path, monkeypatch):
    repo = tmp_path / "private_project"
    repo.mkdir()
    (repo / "x.py").write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    gw = Gateway()

    called = {"cloud": False}

    def boom(*a, **k):
        called["cloud"] = True
        raise AssertionError("cloud client should not be called")

    gw.bifrost_client.chat.completions.create = boom

    with pytest.raises(PrivateModeViolation):
        gw.complete([{"role": "user", "content": "hi"}], tier="cheap")

    assert called["cloud"] is False
