"""Notification payload formatting and template rendering helpers."""

from typing import Dict, Any, Optional


def render_notification_text(template: str, context: Dict[str, Any]) -> str:
    """Substitute dictionary variables into a template string."""
    try:
        return template.format(**context)
    except KeyError:
        return template


def build_push_envelope(title: str, body: str, badge_count: Optional[int] = None) -> Dict[str, Any]:
    """Assemble a standard push notification dispatch payload."""
    payload: Dict[str, Any] = {
        "notification": {
            "title": title.strip(),
            "body": body.strip(),
        },
        "priority": "normal",
    }
    if badge_count is not None:
        payload["notification"]["badge"] = max(0, badge_count)
    return payload


def format_digest_summary(count: int, channel: str = "general") -> str:
    """Generate a one-sentence digest summary for daily updates."""
    plural = "updates" if count != 1 else "update"
    return f"You have {count} unread {plural} in the #{channel} stream."
