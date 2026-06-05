"""
币安广场：按 BTC/ETH/SOL 话题聚合多空占比（过滤喊单/广告，不按单帖计分）。
无官方开放 API 时使用 Reddit 搜索 RSS 作为广场话题代理。
"""

from __future__ import annotations

import logging
import re
from typing import Any

import feedparser
import requests

from collectors.community_sentiment import CommunityPost, classify_sentiment, is_spam
from collectors.news_recency import entry_published_at, get_news_max_age_days, is_datetime_recent

logger = logging.getLogger(__name__)

LANE_QUERIES = {
    "btc": "binance+BTC+bitcoin",
    "eth": "binance+ETH+ethereum",
    "sol": "binance+SOL+solana",
}

_SYMBOL_FILTER = {
    "btc": re.compile(r"\b(btc|bitcoin|\$btc|比特币)\b", re.I),
    "eth": re.compile(r"\b(eth|ethereum|\$eth|以太坊)\b", re.I),
    "sol": re.compile(r"\b(sol|solana|\$sol)\b", re.I),
}


def _fetch_square_api_posts(lane: str, *, timeout: int = 15) -> list[dict[str, Any]]:
    """尝试币安广场内部接口（无指纹时通常为空）。"""
    url = "https://www.binance.com/bapi/composite/v9/friendly/pgc/feed/feed-recommend/list"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "clienttype": "web",
        "lang": "zh-CN",
    }
    try:
        resp = requests.post(url, json={"page": 1, "pageSize": 40}, headers=headers, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data")
        if not data:
            return []
        items = data if isinstance(data, list) else (data.get("list") or data.get("contents") or [])
        return [x for x in items if isinstance(x, dict)]
    except Exception as exc:
        logger.debug("币安广场 API %s: %s", lane, exc)
        return []


def _parse_api_item(raw: dict[str, Any], lane: str) -> CommunityPost | None:
    title = (raw.get("title") or raw.get("contentTitle") or "").strip()
    body = (raw.get("content") or raw.get("text") or raw.get("body") or "")[:800]
    text = f"{title} {body}".strip()
    if not text or is_spam(text):
        return None
    sym = _SYMBOL_FILTER.get(lane)
    if sym and not sym.search(text):
        return None
    return CommunityPost(
        source="币安广场",
        lane=lane,
        title=title[:200],
        text=body,
        url=raw.get("shareUrl") or raw.get("url") or "",
        published_at="",
        feed_key="binance_square",
    )


def _fetch_reddit_square_proxy(lane: str, *, max_items: int = 25) -> list[CommunityPost]:
    q = LANE_QUERIES.get(lane, lane)
    url = f"https://www.reddit.com/search.rss?q={q}&sort=new"
    max_age = get_news_max_age_days()
    posts: list[CommunityPost] = []
    try:
        parsed = feedparser.parse(url, agent="CryptMktBarometer/1.0")
    except Exception:
        return []
    for entry in (parsed.entries or [])[: max_items * 2]:
        title = (entry.get("title") or "").strip()
        if not title or is_spam(title):
            continue
        pub_dt = entry_published_at(entry)
        if not is_datetime_recent(pub_dt, max_age_days=max_age):
            continue
        sym = _SYMBOL_FILTER.get(lane)
        if sym and not sym.search(title):
            continue
        posts.append(
            CommunityPost(
                source="币安广场·话题代理",
                lane=lane,
                title=title,
                text="",
                url=entry.get("link") or "",
                published_at=pub_dt.isoformat() if pub_dt else "",
                feed_key="binance_square_proxy",
            )
        )
        if len(posts) >= max_items:
            break
    return posts


def fetch_binance_square_lane(
    lane: str,
    *,
    max_items: int = 25,
    timeout: int = 15,
    use_proxy: bool = True,
) -> tuple[list[CommunityPost], str]:
    posts: list[CommunityPost] = []
    for raw in _fetch_square_api_posts(lane, timeout=timeout):
        p = _parse_api_item(raw, lane)
        if p:
            posts.append(p)
        if len(posts) >= max_items:
            break
    if posts:
        return posts, f"币安广场API·{len(posts)}条"

    if use_proxy:
        proxy = _fetch_reddit_square_proxy(lane, max_items=max_items)
        return proxy, f"币安广场代理·{len(proxy)}条"
    return [], "币安广场暂无数据"


def aggregate_square_sentiment(posts: list[CommunityPost], lane: str) -> dict[str, Any]:
    """仅统计多空占比，不按单帖打分。"""
    bull = bear = neutral = spam = 0
    for p in posts:
        text = p.full_text()
        if is_spam(text):
            spam += 1
            continue
        s = classify_sentiment(text)
        if s == "bull":
            bull += 1
        elif s == "bear":
            bear += 1
        else:
            neutral += 1
    total = bull + bear + neutral
    ratio = (bull - bear) / total if total else 0.0
    impact = round(max(-2.0, min(2.0, ratio * 2.0)), 2)
    if 0 < abs(impact) < 0.3:
        impact = 0.3 if impact > 0 else -0.3
    return {
        "lane": lane,
        "bullish": bull,
        "bearish": bear,
        "neutral": neutral,
        "spam": spam,
        "total": total,
        "bullish_pct": round(bull / total * 100, 1) if total else 50.0,
        "aggregate_impact": impact,
    }


def fetch_all_binance_square(cfg: dict[str, Any]) -> tuple[dict[str, list[CommunityPost]], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("community", {})
    if not ds.get("binance_square", True):
        return {}, [], []

    max_items = int(cfg.get("collector", {}).get("community_max_items", 25))
    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))
    use_proxy = bool(cfg.get("community", {}).get("binance_square_use_proxy", True))

    by_lane: dict[str, list[CommunityPost]] = {}
    summary: list[str] = []
    errors: list[str] = []

    for lane in ("btc", "eth", "sol"):
        posts, note = fetch_binance_square_lane(
            lane, max_items=max_items, timeout=timeout, use_proxy=use_proxy
        )
        by_lane[lane] = posts
        summary.append(f"广场·{lane.upper()} {note}")

    return by_lane, summary, errors
