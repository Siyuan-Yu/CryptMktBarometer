"""
资讯展示层：中文化 + 分类 TOP 列表（加密池 / 宏观池分离）
"""

from __future__ import annotations

from typing import Any

from collectors.news_categories import select_category_top
from collectors.news_collect import select_top_news
from collectors.news_localize import build_display_fields
from collectors.types import NewsItem


def news_item_to_display(item: NewsItem) -> dict[str, Any]:
    """单条资讯 → 页面/API 用字典（含中文标题、摘要、来源标签）。"""
    base = item.to_display_dict()
    base.update(build_display_fields(item))
    return base


def prepare_all_news_views(
    crypto_items: list[NewsItem],
    macro_items: list[NewsItem] | None = None,
    *,
    top_limit: int = 10,
    category_limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """
    生成 TOP10 与四大分类列表。
    - TOP10：加密 + 宏观合并排序
    - BTC/SOL/ETH：仅加密池
    - 宏观：仅宏观池（剔除加密关键词）
    """
    macro_items = macro_items or []
    combined = crypto_items + macro_items

    return {
        "top": select_top_news(
            combined, limit=top_limit, to_display=news_item_to_display
        ),
        "btc": select_category_top(
            crypto_items,
            "btc",
            limit=category_limit,
            to_display=news_item_to_display,
            pool="crypto",
        ),
        "sol": select_category_top(
            crypto_items,
            "sol",
            limit=category_limit,
            to_display=news_item_to_display,
            pool="crypto",
        ),
        "eth": select_category_top(
            crypto_items,
            "eth",
            limit=category_limit,
            to_display=news_item_to_display,
            pool="crypto",
        ),
        "macro": select_category_top(
            macro_items if macro_items else combined,
            "macro",
            limit=category_limit,
            to_display=news_item_to_display,
            pool="macro" if macro_items else None,
        ),
    }
