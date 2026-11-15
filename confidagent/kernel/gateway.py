"""Kernel Gateway - the ONLY place in the codebase allowed to call an LLM.

All cheap/powerful traffic goes through Bifrost (OpenAI-compatible).
Local-tier traffic is routed directly to Ollama, bypassing Bifrost.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import openai

from kernel.settings import settings


class GatewayError(Exception):
    """Raised after exhausting retries on 429/5xx, or other terminal call failures."""


class GatewayUnavailable(Exception):
    """Raised when Bifrost (or Ollama, for local tier) is unreachable."""


class LocalModelUnavailable(GatewayUnavailable):
    """Raised when the local Ollama model is unreachable. Never silently falls back to cloud."""


class PrivateModeViolation(Exception):
    """Raised when a cloud tier is requested while confidential/local-only mode is enforced."""


# Per-1M-token prices: {"tier": {"in": usd_per_1m_input, "out": usd_per_1m_output}}
MODEL_PRICES: Dict[str, Dict[str, float]] = {
    "cheap": {"in": 0.05, "out": 0.08},
    "powerful": {"in": 0.15, "out": 0.60},
    "local": {"in": 0.0, "out": 0.0},
}


def _load_prices_from_env() -> None:
    """Populate MODEL_PRICES from MODEL_PRICES_JSON in .env if present."""
    raw = os.getenv("MODEL_PRICES_JSON", "")
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("[gateway] MODEL_PRICES_JSON is not valid JSON; using default prices", file=sys.stderr)
        return
    for tier, prices in data.items():
        if tier in MODEL_PRICES and isinstance(prices, dict):
            MODEL_PRICES[tier].update({k: float(v) for k, v in prices.items() if k in ("in", "out")})


_load_prices_from_env()


@dataclass
class CompletionResult:
    """Normalized result of one gateway completion call."""
    text: str
    model_used: str
    provider_used: str          # read from response headers or response.model
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    cache_hit: bool = False     # True if Bifrost served from its semantic cache
    failover_occurred: bool = False
    latency_ms: int = 0
    raw: Any = field(default=None, repr=False)


def make_openai_client(base_url: str, api_key: str) -> "openai.OpenAI":
    """Single factory for openai.OpenAI instances. The only OpenAI( construction site."""
    return openai.OpenAI(base_url=base_url, api_key=api_key)


class Gateway:
    """Single entry point for all LLM calls in the codebase."""

    VALID_TIERS = ("cheap", "powerful", "local")

    def __init__(self) -> None:
        self.bifrost_client = make_openai_client(settings.bifrost_base_url, settings.bifrost_api_key)
        self.ollama_client = make_openai_client(
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "ollama",
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tier: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> CompletionResult:
        """Run one completion through the requested tier."""
        if tier not in self.VALID_TIERS:
            raise GatewayError(f"Unknown tier '{tier}'. Valid tiers: {', '.join(self.VALID_TIERS)}")

        # Confidential/privacy enforcement: block cloud tiers before any network call.
        if tier in ("cheap", "powerful"):
            try:
                from security.privacy_checker import enforce_local
                if enforce_local():
                    raise PrivateModeViolation(
                        "local model required: confidential mode is enforced; cloud tiers are blocked"
                    )
            except ImportError:
                pass

        model = getattr(settings, f"model_{tier}")
        if tier == "local":
            return self._call_local(messages, model, temperature, max_tokens, tools)

        return self._call_bifrost(messages, tier, model, temperature, max_tokens, tools)

    def is_local_available(self) -> bool:
        """True if Ollama responds; cached for 30 seconds."""
        now = time.monotonic()
        cached = getattr(self, "_local_avail_cache", None)
        if cached is not None:
            value, at = cached
            if now - at < 30.0:
                return value
        try:
            models = self.ollama_client.models.list()
            _ = list(models)
            value = True
        except Exception:
            value = False
        self._local_avail_cache = (value, now)
        return value

    def health(self) -> bool:
        """Return True if Bifrost is reachable (GET {base}/models), else warn."""
        base = settings.bifrost_base_url.rstrip("/")
        try:
            models = self.bifrost_client.models.list()
            _ = list(models)  # force iteration to ensure the request actually succeeded
            return True
        except Exception as exc:  # noqa: BLE001 - any failure means unavailable
            print(
                "[gateway] Bifrost unreachable. Start it with: npx -y @maximhq/bifrost "
                f"(tried {base}; error: {exc})",
                file=sys.stderr,
            )
            return False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _call_bifrost(
        self,
        messages: List[Dict[str, Any]],
        tier: str,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
    ) -> CompletionResult:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        backoffs = (1.0, 3.0)
        last_error: Optional[Exception] = None
        for attempt in range(3):  # initial + 2 retries
            start = time.perf_counter()
            try:
                response = self.bifrost_client.chat.completions.create(**kwargs)
                break
            except openai.RateLimitError as exc:
                last_error = exc
            except openai.APIStatusError as exc:
                if exc.status_code is not None and 500 <= exc.status_code < 600:
                    last_error = exc
                else:
                    raise GatewayError(f"Bifrost rejected request ({exc.status_code}): {exc}") from exc
            except openai.APIConnectionError as exc:
                # Connection-level failure: Bifrost itself is likely down.
                raise GatewayUnavailable(
                    "Cannot reach Bifrost. Start it with: npx -y @maximhq/bifrost"
                ) from exc

            if attempt < len(backoffs):
                time.sleep(backoffs[attempt])
        else:
            print("[reliability] provider exhausted; Bifrost will attempt the next provider on the next call", file=sys.stderr)
            raise GatewayError(f"All retries exhausted. Last error: {last_error}")

        latency_ms = int((time.perf_counter() - start) * 1000)
        return self._build_result(
            response,
            tier,
            model,
            requested_tier=tier,
            latency_ms=latency_ms,
            failover_occurred=False,
        )

    def _call_local(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
    ) -> CompletionResult:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            start = time.perf_counter()
            response = self.ollama_client.chat.completions.create(**kwargs)
        except openai.APIConnectionError as exc:
            raise LocalModelUnavailable(
                "Cannot reach Ollama. Start it with: ollama serve "
                "then: ollama pull llama3.2:3b"
            ) from exc
        except openai.RateLimitError as exc:
            raise GatewayError(f"Ollama rate limited: {exc}") from exc
        except openai.APIStatusError as exc:
            raise GatewayError(f"Ollama rejected request ({exc.status_code}): {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        return self._build_result(response, "local", model, requested_tier="local", latency_ms=latency_ms)

    def _build_result(
        self,
        response,
        tier: str,
        requested_model: str,
        *,
        requested_tier: str,
        latency_ms: int,
        failover_occurred: bool = False,
    ) -> CompletionResult:
        choice = response.choices[0]
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

        model_used = response.model or requested_model
        provider_used = self._detect_provider(response, model_used)
        cache_hit = self._detect_cache_hit(response)
        # Failover visibility only applies to Bifrost-routed tiers; the local
        # tier talks to Ollama directly and Ollama may report a bare model name.
        if requested_tier == "local":
            failover_occurred = False
        else:
            failover_occurred = bool(failover_occurred) or (
                model_used != requested_model or provider_used not in ("bifrost", requested_tier)
            )
        cost_usd = self._cost(tier, prompt_tokens, completion_tokens)

        if failover_occurred:
            print(
                f"[gateway] failover: requested={requested_tier} "
                f"served_by={provider_used}/{model_used}",
                file=sys.stderr,
            )

        result = CompletionResult(
            text=choice.message.content or "",
            model_used=model_used,
            provider_used=provider_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cache_hit=cache_hit,
            failover_occurred=failover_occurred,
            latency_ms=latency_ms,
            raw=response,
        )

        # Append one ledger line per call.
        try:
            from kernel import ledger as _ledger  # noqa: PLC0415
            _ledger.record(
                stage="completion",
                tier=tier,
                model=result.model_used,
                provider=result.provider_used,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
                cache_hit=result.cache_hit,
                failover=result.failover_occurred,
                latency_ms=result.latency_ms,
            )
        except Exception:
            pass  # ledger must never break an LLM call

        return result

    @staticmethod
    def _detect_provider(response, model_used: str) -> str:
        """Best-effort provider detection from headers or model string."""
        headers = getattr(response, "headers", None) or {}
        for key in ("x-bifrost-provider", "x-provider", "x-served-by"):
            value = headers.get(key) if hasattr(headers, "get") else None
            if value:
                return str(value)
        lower = model_used.lower()
        if "/" in model_used:
            prefix = lower.split("/", 1)[0]
            known = ("groq", "gemini", "google", "openrouter", "anthropic", "openai", "mistral")
            if prefix in known:
                return prefix
        if "qwen" in lower or "llama" in lower:
            return "ollama"
        return "bifrost"

    @staticmethod
    def _detect_cache_hit(response) -> bool:
        headers = getattr(response, "headers", None) or {}
        if hasattr(headers, "get"):
            for key in ("x-bifrost-cache", "x-cache"):
                if str(headers.get(key, "")).lower() == "hit":
                    return True
        return False

    @staticmethod
    def _cost(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
        prices = MODEL_PRICES.get(tier, {"in": 0.0, "out": 0.0})
        cost = (prompt_tokens / 1_000_000) * prices["in"] + (completion_tokens / 1_000_000) * prices["out"]
        return round(cost, 10)
