"""ConfidAgent Kernel Settings - Single source of truth for configuration."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FeatureFlags:
    """Per-layer feature flags for ablation benchmarking.

    All flags default to on (full stack).  Env overrides: CONFIDAGENT_<NAME>.
    """
    ast_context: bool = True
    file_memory: bool = True
    routing: bool = True
    cache: bool = True
    cost_model: bool = True
    tool_minimization: bool = True


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class AppSettings:
    """Application settings schema with sensible defaults and environment loading."""
    bifrost_base_url: str = "http://localhost:8080/v1"
    bifrost_api_key: str = "sk-bf-local"
    tavily_api_key: str = ""
    model_cheap: str = "openai/gpt-oss-20b"
    model_powerful: str = "openai/gpt-oss-120b"
    model_local: str = "qwen2.5-coder:3b"
    budget_usd: float = 2.00
    cache_threshold: float = 0.90
    cache_ttl_seconds: int = 3600
    compression_target: float = 0.5
    max_context_tokens: int = 6000
    dry_run: bool = False
    local_triage_enabled: bool = True
    cascade_enabled: bool = True
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)

    def __post_init__(self) -> None:
        """Load values from environment variables when present."""
        if "BIFROST_BASE_URL" in os.environ:
            self.bifrost_base_url = os.environ["BIFROST_BASE_URL"]
        if "BIFROST_API_KEY" in os.environ:
            self.bifrost_api_key = os.environ["BIFROST_API_KEY"]
        if "TAVILY_API_KEY" in os.environ:
            self.tavily_api_key = os.environ["TAVILY_API_KEY"]

        if "MODEL_CHEAP" in os.environ:
            self.model_cheap = os.environ["MODEL_CHEAP"]
        elif "GROQ_MODEL_CHEAP" in os.environ:
            self.model_cheap = os.environ["GROQ_MODEL_CHEAP"]

        if "MODEL_POWERFUL" in os.environ:
            self.model_powerful = os.environ["MODEL_POWERFUL"]
        elif "GROQ_MODEL_POWERFUL" in os.environ:
            self.model_powerful = os.environ["GROQ_MODEL_POWERFUL"]

        if "MODEL_LOCAL" in os.environ:
            self.model_local = os.environ["MODEL_LOCAL"]
        elif "OLLAMA_MODEL" in os.environ:
            self.model_local = os.environ["OLLAMA_MODEL"]

        if "CONFIDAGENT_BUDGET_USD" in os.environ:
            try:
                self.budget_usd = float(os.environ["CONFIDAGENT_BUDGET_USD"])
            except ValueError:
                pass
        elif "BUDGET_USD" in os.environ:
            try:
                self.budget_usd = float(os.environ["BUDGET_USD"])
            except ValueError:
                pass

        if "CACHE_THRESHOLD" in os.environ:
            try:
                self.cache_threshold = float(os.environ["CACHE_THRESHOLD"])
            except ValueError:
                pass

        if "CACHE_TTL_SECONDS" in os.environ:
            try:
                self.cache_ttl_seconds = int(os.environ["CACHE_TTL_SECONDS"])
            except ValueError:
                pass

        if "COMPRESSION_TARGET" in os.environ:
            try:
                self.compression_target = float(os.environ["COMPRESSION_TARGET"])
            except ValueError:
                pass

        if "MAX_CONTEXT_TOKENS" in os.environ:
            try:
                self.max_context_tokens = int(os.environ["MAX_CONTEXT_TOKENS"])
            except ValueError:
                pass

        if "DRY_RUN" in os.environ:
            self.dry_run = os.environ["DRY_RUN"].strip().lower() in ("true", "1", "yes")

        if "CONFIDAGENT_LOCAL_TRIAGE" in os.environ:
            self.local_triage_enabled = (
                os.environ["CONFIDAGENT_LOCAL_TRIAGE"].strip().lower() not in ("0", "false", "no")
            )

        if "CONFIDAGENT_CASCADE" in os.environ:
            self.cascade_enabled = (
                os.environ["CONFIDAGENT_CASCADE"].strip().lower() not in ("0", "false", "no")
            )

        self.feature_flags = FeatureFlags(
            ast_context=_env_bool("CONFIDAGENT_AST_CONTEXT", True),
            file_memory=_env_bool("CONFIDAGENT_FILE_MEMORY", True),
            routing=_env_bool("CONFIDAGENT_ROUTING", True),
            cache=_env_bool("CONFIDAGENT_CACHE", True),
            cost_model=_env_bool("CONFIDAGENT_COST_MODEL", True),
            tool_minimization=_env_bool("CONFIDAGENT_TOOL_MINIMIZATION", True),
        )


settings = AppSettings()


def reload() -> AppSettings:
    """Reload environment variables from .env and refresh global settings singleton."""
    global settings
    load_dotenv(override=True)
    settings = AppSettings()
    return settings
