"""Pagination calculators and query parameter extractors."""

import math
from typing import Dict, Any, List


def calculate_offset(page_number: int, page_size: int) -> int:
    """Compute the starting item index for a 1-indexed page."""
    safe_page = max(1, page_number)
    safe_size = max(1, page_size)
    return (safe_page - 1) * safe_size


def build_page_metadata(total_items: int, page_number: int, page_size: int) -> Dict[str, Any]:
    """Build response envelope containing pagination details."""
    safe_page = max(1, page_number)
    safe_size = max(1, page_size)
    total_pages = math.ceil(total_items / safe_size) if total_items > 0 else 1
    return {
        "current_page": safe_page,
        "page_size": safe_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": safe_page < total_pages,
        "has_previous": safe_page > 1,
    }


def paginate_list(items: List[Any], page_number: int, page_size: int) -> List[Any]:
    """Slice a pure in-memory list according to page parameters."""
    offset = calculate_offset(page_number, page_size)
    return items[offset: offset + page_size]
