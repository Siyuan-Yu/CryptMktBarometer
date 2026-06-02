"""
资讯展示层：中文化 + 分类 TOP 列表
"""

from __future__ import annotations

from typing import Any

from collectors.news_categories import select_category_top
from collectors.news_collect import select_top_news
from collectors.news_localize import build_display_fields
from collectors.types import NewsItem


def news_item_to_display(item: NewsItem) -> dict[str, Any]:
    """单条资讯 → 页面/API 用字典（含中文标题、摘要、关键词）。"""
    base = item.to_display_dict()
    base.update(build_display_fields(item))
    return base


def prepare_all_news_views(
    items: list[NewsItem],
    *,
    top_limit: int = 10,
    category_limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """
    生成 TOP10 与三大分类列表。
    分类之间过滤独立，允许与 TOP10 重叠（同属重磅且相关）。
    """
    return {
        "top": select_top_news(items, limit=top_limit, to_display=news_item_to_display),
        "sol": select_category_top(
            items, "sol", limit=category_limit, to_display=news_item_to_display
        ),
        "eth": select_category_top(
            items, "eth", limit=category_limit, to_display=news_item_to_display
        ),
        "macro": select_category_top(
            items, "macro", limit=category_limit, to_display=news_item_to_display
        ),
    }
