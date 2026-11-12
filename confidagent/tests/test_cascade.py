"""Tests for kernel/cascade.py - draft-verify-escalate strategy."""

from kernel.cascade import Gate, CascadeResult, run


def test_gate_check_passes_valid_draft():
    gate = Gate(known_names={"Foo", "Bar"})
    draft = "```python\ndef foo():\n    return Foo\n```\n"
    ok, reason = gate.check(draft, expected_file="mod.py")
    assert ok is True
    assert reason == "pass"


def test_gate_check_missing_file_block():
    gate = Gate()
    ok, reason = gate.check("just text", expected_file="mod.py")
    assert ok is False
    assert reason == "missing_file_block"


def test_gate_check_truncated_empty():
    gate = Gate()
    ok, reason = gate.check("", expected_file=None)
    assert ok is False
    assert reason == "truncated"


def test_gate_check_hallucinated_symbol():
    gate = Gate(known_names={"Known"})
    draft = "```python\nx = UnknownThing\n```\n"
    ok, reason = gate.check(draft)
    assert ok is False
    assert "hallucinated_symbol" in reason


def test_cascade_disabled_single_call(monkeypatch):
    import importlib
    ks_module = importlib.import_module("kernel.settings")
    monkeypatch.setattr(ks_module.settings, "cascade_enabled", False)
    calls = []

    class FakeResult:
        text = "ok"
        total_tokens = 10
        cost_usd = 0.001

    def builder(tier, max_tokens):
        calls.append(tier)
        return FakeResult()

    res = run(builder)
    assert res.tier_used == "cheap"
    assert res.escalations == 0
    assert calls == ["cheap"]


def test_cascade_draft_passes_no_escalation():
    calls = []

    class FakeResult:
        text = "```python\ndef foo():\n    return 1\n```\n"
        total_tokens = 10
        cost_usd = 0.001

    def builder(tier, max_tokens):
        calls.append(tier)
        return FakeResult()

    res = run(builder, expected_file="mod.py", known_names=set())
    assert res.tier_used in ("cheap", "local")
    assert res.escalations == 0
