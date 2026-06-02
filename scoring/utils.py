"""
计分工具函数
"""

from __future__ import annotations

import re
from typing import Iterable

from collectors.types import NewsItem


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def map_impact_to_points(avg_impact: float, max_points: float) -> float:
    """
    将单条影响分均值（约 -10 ~ +10）映射到分项得分（0 ~ max_points）。
    中性 impact=0 对应 max_points/2。
    """
    return clamp(max_points * (avg_impact + 10.0) / 20.0, 0.0, max_points)


def filter_news_by_keywords(
    items: Iterable[NewsItem],
    keywords: tuple[str, ...],
) -> list[NewsItem]:
    matched: list[NewsItem] = []
    for item in items:
        title = item.title.lower()
        if any(kw in title for kw in keywords):
            matched.append(item)
    return matched


def avg_impact(items: list[NewsItem]) -> float:
    if not items:
        return 0.0
    return sum(n.impact_score for n in items) / len(items)


def top_impact_sum(items: list[NewsItem], n: int = 5) -> float:
    """取影响分绝对值最高的 n 条求均值，突出重磅消息。"""
    if not items:
        return 0.0
    sorted_items = sorted(items, key=lambda x: abs(x.impact_score), reverse=True)
    top = sorted_items[:n]
    return sum(i.impact_score for i in top) / len(top)


def parse_signed_percent(text: str) -> float | None:
    """从文案中解析带符号百分比，如 '+2.50%'、'-1.2%'。"""
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None
