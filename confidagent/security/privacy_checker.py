import os
import re
from dotenv import load_dotenv

load_dotenv()

INJECTION_PHRASES = [
    "ignore confidential",
    "use cloud",
    "disable privacy",
    "bypass approval",
    "skip approval",
    "send to cloud",
    "override security",
    "bypass",
    "ignore privacy",
    "disable confidential",
    "use cloud model",
    "skip privacy",
    "override confidential",
]

_INJECTION_RE = re.compile(
    "|".join(re.escape(p) for p in [
        "ignore confidential",
        "use cloud",
        "disable privacy",
        "bypass approval",
        "skip approval",
    ]),
    re.IGNORECASE,
)


def sanitize_untrusted_text(text: str, context: str = "") -> str:
    """Redact prompt-injection phrases and log each attempt."""
    if not isinstance(text, str) or not text:
        return text
    matches = list(_INJECTION_RE.finditer(text))
    if not matches:
        return text
    for m in matches:
        phrase = m.group(0)
        where = f" in {context}" if context else ""
        print(f"[security] injection attempt blocked{where}: {phrase}")
    return _INJECTION_RE.sub("[REDACTED]", text)


def enforce_local(repo_path: str = None) -> bool:
    """Return True when local-only/private mode must be enforced."""
    repo_path = repo_path or os.getcwd()
    try:
        if os.path.exists(os.path.join(repo_path, ".confidential")):
            return True
    except Exception:
        pass
    try:
        repo_name = os.path.basename(os.path.abspath(repo_path)).lower()
        if any(word in repo_name for word in ["private", "confidential", "secret", "internal"]):
            return True
    except Exception:
        pass
    try:
        env_path = os.path.join(repo_path, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if re.search(r"(?m)^\s*CONFIDENTIAL\s*=\s*true\s*$", content, re.IGNORECASE):
                return True
    except Exception:
        pass
    # Also honor process-level flag for explicit --confidential runs.
    if os.getenv("CONFIDENTIAL", "").strip().lower() == "true":
        return True
    return False


class PrivacyChecker:

    def __init__(self, repo_path: str, force_confidential: bool = False):
        self.repo_path = repo_path
        self.force_confidential = force_confidential

    def is_confidential(self) -> bool:
        if self.force_confidential:
            return True
        return enforce_local(self.repo_path)

    def check_injection(self, prompt: str) -> bool:
        prompt_lower = (prompt or "").lower()
        return any(phrase in prompt_lower for phrase in INJECTION_PHRASES)
