"""
采集模块通用数据结构
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NewsItem:
    """统一资讯条目，供 TOP10 筛选与页面展示。"""

    title: str
    source: str
    url: str
    impact_score: float = 0.0
    keywords: list[str] = field(default_factory=list)
    logic: str = ""
    published_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "impact_score": round(self.impact_score, 1),
            "keywords": self.keywords[:3],
            "logic": self.logic,
        }
