"""
资讯采集汇总
按 config 开关调用各资讯源，合并后按影响分绝对值取 TOP10。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.news_cryptopanic import fetch_cryptopanic
from collectors.news_rss import fetch_rss_by_key
from collectors.types import NewsItem

logger = logging.getLogger(__name__)


def select_top_news(
    items: list[NewsItem],
    limit: int = 10,
    *,
    to_display=None,
) -> list[dict[str, Any]]:
    """按影响分值绝对值降序，取前 N 条。"""
    convert = to_display or (lambda n: n.to_display_dict())
    sorted_items = sorted(items, key=lambda x: abs(x.impact_score), reverse=True)
    return [convert(n) for n in sorted_items[:limit]]


def collect_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    """
    拉取所有已启用的资讯源。
    :return: (全部资讯, 成功摘要行, 错误列表)
    """
    ds = cfg.get("data_sources", {}).get("news", {})
    api_keys = cfg.get("api_keys", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_max_items", 30))
    rss_urls = collector_cfg.get("rss", {})

    all_items: list[NewsItem] = []
    summary_lines: list[str] = []
    errors: list[str] = []

    if ds.get("cryptopanic", False):
        items, err = fetch_cryptopanic(
            api_keys.get("cryptopanic", ""),
            timeout=timeout,
        )
        if err:
            if "未配置" in err or "已跳过" in err:
                summary_lines.append(err)
            else:
                errors.append(err)
                summary_lines.append(f"CryptoPanic：失败")
        else:
            all_items.extend(items)
            summary_lines.append(f"CryptoPanic：{len(items)} 条")

    for key in ("coindesk", "theblock"):
        if not ds.get(key, False):
            continue
        items, err = fetch_rss_by_key(
            key,
            rss_urls,
            timeout=timeout,
            max_items=max_rss,
        )
        if err:
            errors.append(err)
            summary_lines.append(f"{key}：失败")
        else:
            all_items.extend(items)
            name = "CoinDesk" if key == "coindesk" else "The Block"
            summary_lines.append(f"{name}：{len(items)} 条")

    logger.info("资讯合计 %d 条，来源摘要 %s", len(all_items), summary_lines)
    return all_items, summary_lines, errors
