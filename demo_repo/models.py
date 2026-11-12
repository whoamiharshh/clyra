"""Domain entity structures for content publishing."""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class MemberProfile:
    """Member account basic profile details."""
    member_id: str
    display_name: str
    email_address: str
    is_active: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class ArticleItem:
    """Published article item entity."""
    article_id: str
    author_id: str
    title: str
    content_body: str
    published_at: Optional[datetime] = None
    view_count: int = 0
