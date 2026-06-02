"""
RSS 资讯采集（CoinDesk、The Block 等）
使用 feedparser 解析公开 RSS，无需 API Key。
"""

from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from collectors.news_impact import score_from_title
from collectors.types import NewsItem

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
}


def fetch_rss_feed(
    source_name: str,
    feed_url: str,
    *,
    timeout: int = 15,
    max_items: int = 30,
) -> tuple[list[NewsItem], str | None]:
    """
    解析单个 RSS 源。
    :return: (资讯列表, 错误信息)
    """
    if not feed_url:
        return [], f"{source_name}：未配置 RSS 地址"

    try:
        parsed = feedparser.parse(
            feed_url,
            agent="CryptMktBarometer/1.0",
            request_headers={"User-Agent": "CryptMktBarometer/1.0"},
        )
    except Exception as exc:
        logger.warning("%s RSS 解析失败: %s", source_name, exc)
        return [], f"{source_name}：{exc}"

    if getattr(parsed, "bozo", False) and not parsed.entries:
        err = getattr(parsed, "bozo_exception", None)
        return [], f"{source_name}：RSS 解析异常 {err}"

    items: list[NewsItem] = []
    for entry in (parsed.entries or [])[:max_items]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue

        url = entry.get("link") or ""
        published = ""
        if entry.get("published"):
            try:
                published = parsedate_to_datetime(entry["published"]).isoformat()
            except Exception:
                published = str(entry.get("published", ""))

        impact, keywords, logic = score_from_title(title)
        items.append(
            NewsItem(
                title=title,
                source=source_name,
                url=url,
                impact_score=impact,
                keywords=keywords,
                logic=logic,
                published_at=published,
                raw=dict(entry),
            )
        )

    return items, None


def fetch_rss_by_key(
    source_key: str,
    feed_urls: dict[str, Any],
    *,
    timeout: int = 15,
    max_items: int = 30,
) -> tuple[list[NewsItem], str | None]:
    """根据 config 中的 key 读取对应 RSS URL。"""
    mapping = {
        "coindesk": ("CoinDesk", feed_urls.get("coindesk") or DEFAULT_FEEDS["CoinDesk"]),
        "theblock": ("The Block", feed_urls.get("theblock") or DEFAULT_FEEDS["The Block"]),
    }
    if source_key not in mapping:
        return [], f"未知 RSS 源：{source_key}"
    name, url = mapping[source_key]
    return fetch_rss_feed(name, str(url), timeout=timeout, max_items=max_items)
