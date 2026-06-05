"""
RSS 资讯采集（CoinDesk、The Block 等）
使用 feedparser 解析公开 RSS，无需 API Key。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from collectors.news_recency import entry_published_at, get_news_max_age_days, is_datetime_recent

from collections.abc import Callable

from collectors.news_impact import score_from_title
from collectors.news_impact_v2 import score_from_title_v2
from collectors.types import NewsItem
from core.config_loader import load_config

ScoreFn = Callable[[str], tuple[float, list[str], str]]

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
    "CoinGlass": "https://www.coinglass.com/feed",
    "Solana生态": "https://solana.com/news/rss.xml",
    "以太坊生态": "https://blog.ethereum.org/feed.xml",
}


def _use_v2_scoring() -> bool:
    return bool(load_config().get("scoring", {}).get("use_news_v2", True))


def fetch_rss_feed(
    source_name: str,
    feed_url: str,
    *,
    timeout: int = 15,
    max_items: int = 30,
    feed_type: str = "crypto",
    score_fn: ScoreFn | None = None,
    asset_lane: str = "",
    source_tier: str = "aggregate",
    feed_key: str = "",
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

    max_age_days = get_news_max_age_days()
    entries = list(parsed.entries or [])
    entries.sort(
        key=lambda e: entry_published_at(e) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    items: list[NewsItem] = []
    for entry in entries:
        if len(items) >= max_items:
            break
        title = (entry.get("title") or "").strip()
        if not title:
            continue

        url = entry.get("link") or ""
        pub_dt = entry_published_at(entry)
        published = pub_dt.isoformat() if pub_dt else ""
        if not is_datetime_recent(pub_dt, max_age_days=max_age_days):
            continue

        if score_fn:
            score = score_fn
        elif _use_v2_scoring():
            score = lambda t: score_from_title_v2(
                t,
                feed_type=feed_type,
                source_tier=source_tier,
                feed_key=feed_key,
            )
        else:
            score = score_from_title
        impact, keywords, logic = score(title)
        raw = dict(entry)
        raw["asset_lane"] = asset_lane
        raw["source_tier"] = source_tier
        raw["feed_key"] = feed_key
        items.append(
            NewsItem(
                title=title,
                source=source_name,
                url=url,
                impact_score=impact,
                keywords=keywords,
                logic=logic,
                published_at=published,
                raw=raw,
                feed_type=feed_type,
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
    """兼容历史抓取模块的旧接口。"""
    lane_map = {"coindesk": ("btc", "authority"), "theblock": ("eth", "authority")}
    asset_lane, tier = lane_map.get(source_key, ("", "aggregate"))
    name = source_key
    url = str(feed_urls.get(source_key) or DEFAULT_FEEDS.get(name, ""))
    return fetch_rss_lane_feed(
        source_key,
        name,
        url,
        asset_lane=asset_lane,
        source_tier=tier,
        timeout=timeout,
        max_items=max_items,
    )


def fetch_rss_lane_feed(
    feed_key: str,
    display_name: str,
    feed_url: str,
    *,
    asset_lane: str,
    source_tier: str = "authority",
    timeout: int = 15,
    max_items: int = 30,
) -> tuple[list[NewsItem], str | None]:
    return fetch_rss_feed(
        display_name,
        feed_url,
        timeout=timeout,
        max_items=max_items,
        feed_type="crypto",
        asset_lane=asset_lane,
        source_tier=source_tier,
        feed_key=feed_key,
    )
