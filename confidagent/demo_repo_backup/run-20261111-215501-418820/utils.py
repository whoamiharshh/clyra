"""General text and formatting utility helpers."""

import re
from datetime import datetime
from typing import Optional


def slugify(text: str) -> str:
    """Convert arbitrary title text into a clean URL slug."""
    lowered = text.lower().strip()
    cleaned = re.sub(r"[^\w\s-]", "", lowered)
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate long text to a maximum length appending a suffix if clipped."""
    if len(text) <= max_length:
        return text
    cutoff = max_length - len(suffix)
    return text[:cutoff] + suffix


def format_iso_date(dt: Optional[datetime] = None) -> str:
    """Format a datetime instance into a standardized human-readable string."""
    target = dt or datetime.utcnow()
    return target.strftime("%Y-%m-%d %H:%M:%S UTC")
