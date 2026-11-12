"""Kernel Compress - LLMLingua-2 prompt compression for code excerpts ONLY.

Hard rule: never compress system prompts, decision instructions, tool schemas,
or approval text. Only large code excerpts inserted into prompts are compressed.
"""

import os
from typing import Dict, Iterable, List, Optional, Tuple

from kernel.context import tokens as _tok
from kernel.settings import settings

MIN_TOKENS_TO_COMPRESS = 400
MAX_STRUCTURED_KEYWORDS = 40  # 'def '/'class ' occurrences above this -> skip

_compress_model = None
_model_failed = False


def available() -> bool:
    """True when llmlingua (+ torch backend) is importable."""
    global _model_failed
    if _model_failed:
        return False
    try:
        import llmlingua  # noqa: F401
        return True
    except Exception:
        return False


def _get_model():
    """Lazy-load and cache the LLMLingua-2 compressor at module level."""
    global _compress_model, _model_failed
    if _compress_model is not None:
        return _compress_model
    if _model_failed:
        return None
    try:
        from llmlingua import PromptCompressor
        _compress_model = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
        return _compress_model
    except Exception:
        _model_failed = True
        return None


def _passes_guardrails(text: str) -> bool:
    if _tok(text) < MIN_TOKENS_TO_COMPRESS:
        return False
    keyword_hits = text.count("def ") + text.count("class ")
    if keyword_hits > MAX_STRUCTURED_KEYWORDS:
        return False
    return True


def compress_code(text: str, target_ratio: float = None, preserve: Iterable[str] = ()) -> Tuple[str, Dict]:
    """Compress one code excerpt to ~target_ratio of its tokens.

    Returns (text, meta_dict). On any failure the input is returned unchanged
    with a 'skipped' reason — compression must never break a run.
    Strings in `preserve` are returned untouched (hard rule).
    """
    target_ratio = target_ratio if target_ratio is not None else settings.compression_target
    preserved: List[str] = [p for p in (preserve or ()) if p]

    if preserved and text in preserved:
        return text, {"skipped": "preserve_list"}

    if not available():
        return text, {"skipped": "llmlingua_not_installed"}

    if not _passes_guardrails(text):
        return text, {"skipped": "guardrails"}

    orig_tokens = _tok(text)
    model = _get_model()
    if model is None:
        return text, {"skipped": "llmlingua_not_installed"}

    try:
        result = model.compress_prompt(
            [text],
            rate=target_ratio,
            force_tokens=["\n", "def", "class", "import", "return"],
        )
        compressed = result.get("compressed_prompt", "") if isinstance(result, dict) else str(result)
    except Exception as exc:
        return text, {"skipped": f"compress_error:{type(exc).__name__}"}

    if not compressed or not compressed.strip():
        return text, {"skipped": "empty_result"}

    new_tokens = _tok(compressed)
    ratio = (new_tokens / orig_tokens) if orig_tokens else 1.0
    return compressed, {"orig_tokens": orig_tokens, "new_tokens": new_tokens, "ratio": round(ratio, 3)}


def compress_snippets(snippets: List[str], target_ratio: float = None, preserve: Iterable[str] = ()) -> Tuple[List[str], Dict]:
    """Compress a list of code excerpts; returns (new_list, aggregate_meta)."""
    preserved = list(preserve or [])
    out: List[str] = []
    total_orig = 0
    total_new = 0
    applied = 0
    for snip in snippets:
        if snip in preserved:
            out.append(snip)
            continue
        new, meta = compress_code(snip, target_ratio)
        if "skipped" in meta:
            out.append(snip)
            continue
        out.append(new)
        total_orig += meta["orig_tokens"]
        total_new += meta["new_tokens"]
        applied += 1
    meta: Dict[str, object] = {"applied": applied}
    if applied:
        meta.update({
            "orig_tokens": total_orig,
            "new_tokens": total_new,
            "ratio": round(total_new / total_orig, 3) if total_orig else 1.0,
        })
    else:
        meta.update({"skipped": "nothing_compressed"})
    return out, meta


def maybe_log(meta: Dict, label: str = "snippets") -> None:
    """Print the one-line compression report when compression actually applied."""
    if "orig_tokens" in meta:
        print(f"[compress] {label} {meta['orig_tokens']:,} -> {meta['new_tokens']:,} tokens ({meta['ratio']:.2f})")


# Explicit contract: these prompt components must NEVER reach compress_code.
NEVER_COMPRESS = {
    "system_prompts", "decision_instructions", "tool_schemas", "approval_text",
}
