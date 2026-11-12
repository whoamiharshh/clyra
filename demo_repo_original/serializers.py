"""Data serialization and conversion primitives."""

from typing import Dict, Any, List
from models import MemberProfile, ArticleItem


def member_to_dict(member: MemberProfile) -> Dict[str, Any]:
    """Convert a MemberProfile instance into a dictionary."""
    return {
        "member_id": member.member_id,
        "display_name": member.display_name,
        "email_address": member.email_address,
        "is_active": member.is_active,
        "tags": list(member.tags),
    }


def article_to_dict(article: ArticleItem) -> Dict[str, Any]:
    """Convert an ArticleItem instance into a dictionary."""
    return {
        "article_id": article.article_id,
        "author_id": article.author_id,
        "title": article.title,
        "content_body": article.content_body,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "view_count": article.view_count,
    }


def serialize_collection(items: List[Any], serializer_func: Any) -> List[Dict[str, Any]]:
    """Map a serialization helper over a collection of items."""
    return [serializer_func(item) for item in items]
