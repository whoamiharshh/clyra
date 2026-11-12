"""Agent triage - classify tasks as analysis vs generation.

Token-heavy, low-reasoning classification runs on the local Ollama model;
cloud calls are reserved for real code generation.
"""

import re
from typing import Optional

ANALYSIS_WORDS = ("explain", "list", "find", "summarize", "which files")


def heuristic_classify(task: str) -> str:
    """Regex fallback when Ollama is unavailable."""
    t = task.lower()
    for word in ANALYSIS_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", t):
            return "analysis"
    return "generation"


def _local_classify(task: str, the_map: str) -> Optional[str]:
    """Ask the local model; returns 'analysis'/'generation' or None on any failure."""
    try:
        from kernel.gateway import Gateway
        g = Gateway()
        if not g.is_local_available():
            print("[triage] Ollama unavailable, using regex heuristic for task classification")
            return None
        messages = [
            {
                "role": "user",
                "content": (
                    "Classify this coding task. Answer with exactly one word: "
                    "'analysis' (read/search/summarize/explain) or 'generation' "
                    "(write/change code).\n\n"
                    f"TASK: {task}\n\nREPO MAP (truncated):\n{the_map[:1200]}"
                ),
            }
        ]
        result = g.complete(messages, tier="local", temperature=0.0, max_tokens=200)
        word = (result.text or "").strip().split()
        if not word:
            return None
        first = word[0].strip(".,!:;'\"").lower()
        if first.startswith("analy"):
            return "analysis"
        if first.startswith("gen"):
            return "generation"
        return None
    except Exception:
        return None


def classify_task(task: str, repo_map: str = "") -> str:
    """Return 'analysis' or 'generation'. Local model first, regex heuristic fallback."""
    result = _local_classify(task, repo_map)
    if result is not None:
        return result
    return heuristic_classify(task)
