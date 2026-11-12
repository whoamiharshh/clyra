"""Structured event logging and formatting configuration."""

import json
import logging
from datetime import datetime
from typing import Any, Dict


class JsonLogFormatter(logging.Formatter):
    """Format standard log records into JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_service_logger(name: str = "app_service") -> logging.Logger:
    """Create a configured logger instance with the json formatter."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    return logger
