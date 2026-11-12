"""Asynchronous background job processors and maintenance tasks."""

import time
from typing import Dict, Any, List


def send_welcome_email(recipient_email: str, recipient_name: str) -> Dict[str, Any]:
    """Simulate dispatching a welcome onboarding email message."""
    time.sleep(0.01)
    return {
        "status": "dispatched",
        "recipient": recipient_email,
        "name": recipient_name,
        "sent_at": time.time(),
    }


def purge_old_cache_entries(cache_instance: Any) -> int:
    """Clear expired items from an active cache backend."""
    purged_count = 0
    if hasattr(cache_instance, "_store"):
        now = time.time()
        keys_to_remove = [k for k, (_, exp) in cache_instance._store.items() if now > exp]
        for key in keys_to_remove:
            del cache_instance._store[key]
            purged_count += 1
    return purged_count


def process_batch_notifications(recipients: List[str], message: str) -> int:
    """Process a list of recipients for bulk announcement delivery."""
    delivered = 0
    for email in recipients:
        if "@" in email:
            delivered += 1
    return delivered
