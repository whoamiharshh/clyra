"""Kernel Cascade - draft-verify-escalate execution strategy.

A cheap (or local) model drafts, a deterministic gate decides, and only
rejected drafts pay for the powerful model. No LLM calls inside the gate.

Every gateway call made through a cascade is recorded by the gateway itself
(kernel.gateway -> kernel.ledger.record), so benchmarks can separate draft
cost from escalation cost by tier.
"""

import ast
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Set, Tuple

_BUILTIN_NAMES: Set[str] = {
    # literals / common builtins that legitimately appear as CamelCase-ish tokens
    "None", "True", "False", "NotImplemented", "Ellipsis",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "OSError", "IOError",
    "FileNotFoundError", "NotImplementedError", "ZeroDivisionError",
    "OverflowError", "ArithmeticError", "LookupError", "NameError",
    "AssertionError", "EOFError", "ImportError", "ModuleNotFoundError",
    "UnicodeDecodeError", "UnicodeEncodeError", "JSONDecodeError",
    "BaseException", "GeneratorExit", "KeyboardInterrupt", "SystemExit",
    "Warning", "UserWarning", "DeprecationWarning", "PendingDeprecationWarning",
    "TimeoutError", "ConnectionError", "PermissionError", "IsADirectoryError",
    "int", "float", "str", "bytes", "bool", "list", "dict", "set", "tuple",
    "Dict", "List", "Set", "Tuple", "Optional", "Union", "Any", "Callable",
    "Iterable", "Iterator", "Mapping", "Sequence", "Type", "TypeVar", "Class",
    "Self", "Final", "Literal", "Protocol", "IO", "TextIO", "BinaryIO",
    "Path", "UUID", "Enum", "IntEnum", "StrEnum", "Dataclass", "ABC",
    "NamedTuple", "TypedEnum", "ISO", "UTF", "ASCII", "HTTP", "HTTPS", "URL",
    "URI", "API", "SDK", "CLI", "JSON", "XML", "SQL", "CSV", "HTML", "SSL",
    "TLS", "TCP", "UDP", "DNS", "JWT", "SHA", "MD5", "AES", "RSA", "PEM",
}


def _extract_code_block(draft: str) -> Optional[str]:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", draft or "", re.DOTALL)
    return m.group(1) if m else None


class Gate:
    """Deterministic draft gate. No LLM calls."""

    def __init__(self, known_names: Optional[Set[str]] = None) -> None:
        self.known_names = set(known_names or ()) | set(_BUILTIN_NAMES)

    def check(self, draft: str, expected_file: Optional[str] = None) -> Tuple[bool, str]:
        """Return (ok, reason). reason is 'pass' or a short failure tag."""
        draft = draft or ""
        block = _extract_code_block(draft)

        # 1. Structural checks tied to the expected output file.
        if expected_file:
            if block is None:
                return False, "missing_file_block"
            try:
                ast.parse(block)
            except SyntaxError as exc:
                return False, f"syntax: {exc.msg} (line {exc.lineno})"

        # 2. Truncation: payload must end with a newline and have balanced quotes.
        payload = block if block is not None else draft
        if not payload:
            return False, "truncated"
        if not payload.endswith("\n"):
            return False, "truncated"
        for quote in ('"""', "'''"):
            if payload.count(quote) % 2 == 1:
                return False, "truncated"

        # 3. Hallucinated symbols: CamelCase identifiers must be known.
        for ident in re.findall(r"\b[A-Z][A-Za-z0-9_]{3,}\b", payload):
            if ident not in self.known_names:
                return False, f"hallucinated_symbol:{ident}"

        return True, "pass"


@dataclass
class CascadeResult:
    text: str
    tier_used: str
    escalations: int
    gate_reason: str
    total_cost_usd: float = 0.0
    total_tokens: int = 0


def _pick_draft_tier(gateway, allow_local: bool) -> str:
    from kernel.settings import settings
    if allow_local and getattr(settings, "local_triage_enabled", True):
        try:
            if gateway.is_local_available():
                return "local"
        except Exception:
            pass
    return "cheap"


def run(
    prompt_builder: Callable[[str, int], Any],
    expected_file: Optional[str] = None,
    known_names: Optional[Set[str]] = None,
    max_escalations: int = 1,
    decision_name: str = "decision",
    gateway: Optional[Any] = None,
    allow_local: bool = True,
    max_tokens: int = 2000,
) -> CascadeResult:
    """Draft on a cheap/local tier, gate deterministically, escalate if rejected.

    prompt_builder(tier, max_tokens) must perform one completion and return an
    object with .text, .total_tokens and .cost_usd (e.g. CompletionResult).
    Ledger recording happens inside the gateway, per call.
    """
    from kernel.settings import settings
    if not getattr(settings, "cascade_enabled", True):
        # Cascade disabled: single direct call through whatever tier is cheapest.
        result = prompt_builder("cheap", max_tokens)
        return CascadeResult(
            text=getattr(result, "text", str(result)),
            tier_used="cheap",
            escalations=0,
            gate_reason="disabled",
            total_cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
            total_tokens=int(getattr(result, "total_tokens", 0) or 0),
        )

    if gateway is None:
        from kernel.gateway import Gateway
        gateway = Gateway()

    gate = Gate(known_names)
    draft_tier = _pick_draft_tier(gateway, allow_local)

    total_cost = 0.0
    total_tokens = 0

    def _attempt(tier: str) -> Tuple[str, bool, str]:
        nonlocal total_cost, total_tokens
        try:
            result = prompt_builder(tier, max_tokens)
        except Exception as exc:  # noqa: BLE001 - a failed call counts as a gate failure
            return "", False, f"error:{type(exc).__name__}"
        total_cost += float(getattr(result, "cost_usd", 0.0) or 0.0)
        total_tokens += int(getattr(result, "total_tokens", 0) or 0)
        text = getattr(result, "text", "") or ""
        ok, reason = gate.check(text, expected_file)
        return text, ok, reason

    text, ok, reason = _attempt(draft_tier)
    print(f"[cascade] {decision_name}: draft={draft_tier} "
          f"gate={'pass' if ok else 'fail:' + reason} escalations=0")
    if ok:
        return CascadeResult(text, draft_tier, 0, "pass", total_cost, total_tokens)

    for attempt in range(1, max_escalations + 1):
        text, ok, reason = _attempt("powerful")
        print(f"[cascade] {decision_name}: draft=powerful "
              f"gate={'pass' if ok else 'fail:' + reason} escalations={attempt}")
        if ok:
            return CascadeResult(text, "powerful", attempt, "pass", total_cost, total_tokens)

    print(
        f"[cascade] WARNING: {decision_name} still fails gate after "
        f"{max_escalations} escalation(s) ({reason}); returning powerful draft anyway",
        file=sys.stderr,
    )
    return CascadeResult(text, "powerful", max_escalations, reason, total_cost, total_tokens)
