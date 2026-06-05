"""
Reddit 社区：r/Bitcoin、r/ethereum、r/solana 官方板块 RSS。
"""

from __future__ import annotations

import logging
from typing import Any

import feedparser

from collectors.community_sentiment import CommunityPost
from collectors.news_recency import entry_published_at, get_news_max_age_days, is_datetime_recent

logger = logging.getLogger(__name__)

REDDIT_FEEDS: tuple[tuple[str, str, str], ...] = (
    ("reddit_btc", "btc", "https://www.reddit.com/r/Bitcoin/.rss"),
    ("reddit_eth", "eth", "https://www.reddit.com/r/ethereum/.rss"),
    ("reddit_sol", "sol", "https://www.reddit.com/r/solana/.rss"),
)


def fetch_reddit_lane(
    lane: str,
    feed_url: str,
    *,
    feed_key: str,
    max_items: int = 25,
    timeout: int = 15,
) -> tuple[list[CommunityPost], str | None]:
    try:
        parsed = feedparser.parse(
            feed_url,
            agent="CryptMktBarometer/1.0",
            request_headers={"User-Agent": "CryptMktBarometer/1.0"},
        )
    except Exception as exc:
        return [], str(exc)

    if getattr(parsed, "bozo", False) and not parsed.entries:
        return [], f"Reddit RSS 解析失败 {getattr(parsed, 'bozo_exception', '')}"

    max_age = get_news_max_age_days()
    posts: list[CommunityPost] = []
    for entry in parsed.entries or []:
        if len(posts) >= max_items:
            break
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        pub_dt = entry_published_at(entry)
        if not is_datetime_recent(pub_dt, max_age_days=max_age):
            continue
        summary = ""
        if entry.get("summary"):
            summary = str(entry.get("summary", ""))[:500]
        posts.append(
            CommunityPost(
                source=f"Reddit·r/{lane}",
                lane=lane,
                title=title,
                text=summary,
                url=entry.get("link") or "",
                published_at=pub_dt.isoformat() if pub_dt else "",
                feed_key=feed_key,
            )
        )
    return posts, None


def fetch_all_reddit(
    cfg: dict[str, Any],
    *,
    max_items: int = 25,
    timeout: int = 15,
) -> tuple[list[CommunityPost], list[str], list[str]]:
    rss = cfg.get("collector", {}).get("rss", {}) or {}
    ds = cfg.get("data_sources", {}).get("community", {})
    all_posts: list[CommunityPost] = []
    summary: list[str] = []
    errors: list[str] = []

    if not ds.get("reddit", True):
        return [], [], []

    for key, lane, default_url in REDDIT_FEEDS:
        url = str(rss.get(key) or default_url).strip()
        posts, err = fetch_reddit_lane(lane, url, feed_key=key, max_items=max_items, timeout=timeout)
        if err:
            errors.append(err)
            summary.append(f"Reddit·{lane.upper()}：失败")
        else:
            all_posts.extend(posts)
            summary.append(f"Reddit·{lane.upper()}：{len(posts)} 条")

    return all_posts, summary, errors
