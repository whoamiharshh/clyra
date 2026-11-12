"""Field validation and sanity verification routines."""

import re
from typing import Tuple


EMAIL_REGEX = re.compile(r"^[\w\.\+-]+@[\w\.-]+\.[a-zA-Z]{2,}$")


def validate_email_address(value: str) -> Tuple[bool, str]:
    """Check whether a given string is a syntactically valid email."""
    trimmed = value.strip()
    if not trimmed:
        return False, "Email address cannot be empty."
    if not EMAIL_REGEX.match(trimmed):
        return False, "Email address format is invalid."
    return True, ""


def validate_text_length(text: str, min_len: int = 1, max_len: int = 255) -> Tuple[bool, str]:
    """Verify that a string falls within the allowed character boundaries."""
    length = len(text.strip())
    if length < min_len:
        return False, f"Text must contain at least {min_len} characters."
    if length > max_len:
        return False, f"Text cannot exceed {max_len} characters."
    return True, ""
