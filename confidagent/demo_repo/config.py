"""Application settings and operational defaults."""

import os
from typing import Dict, Any


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 30
SERVICE_NAME = "catalog-web-service"
DEFAULT_TIMEZONE = "UTC"


class RuntimeSettings:
    """Read configuration from environment variables with sensible defaults."""

    def __init__(self) -> None:
        self.service_name = os.getenv("APP_SERVICE_NAME", SERVICE_NAME)
        self.page_limit = int(os.getenv("MAX_PAGE_LIMIT", str(MAX_PAGE_SIZE)))
        self.timeout = int(os.getenv("DEFAULT_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))

    def as_dict(self) -> Dict[str, Any]:
        """Export settings as a dictionary representation."""
        return {
            "service_name": self.service_name,
            "page_limit": self.page_limit,
            "timeout_seconds": self.timeout,
        }
