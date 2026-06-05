"""
X(Twitter) 社区：官方账号 + 分析师（经 RSSHub 等公开 RSS 桥接，无 API Key）。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import feedparser

from collectors.community_sentiment import CommunityPost
from collectors.news_recency import entry_published_at, get_news_max_age_days, is_datetime_recent

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNTS: dict[str, list[str]] = {
    "btc": ["Bitcoin", "saylor", "ARKInvest"],
    "eth": ["ethereum", "VitalikButerin", "bankless"],
    "sol": ["solana", "marinadefinance", "JupiterExchange"],
}


def _twitter_rss_url(base: str, username: str) -> str:
    base = base.rstrip("/")
    user = quote(username.lstrip("@"))
    return f"{base}/twitter/user/{user}"


def fetch_twitter_lane(
    lane: str,
    accounts: list[str],
    *,
    rsshub_base: str,
    max_items_per_user: int = 8,
) -> tuple[list[CommunityPost], list[str]]:
    max_age = get_news_max_age_days()
    posts: list[CommunityPost] = []
    errors: list[str] = []

    for account in accounts:
        url = _twitter_rss_url(rsshub_base, account)
        try:
            parsed = feedparser.parse(
                url,
                agent="CryptMktBarometer/1.0",
                request_headers={"User-Agent": "CryptMktBarometer/1.0"},
            )
        except Exception as exc:
            errors.append(f"@{account}:{exc}")
            continue
        if not parsed.entries:
            errors.append(f"@{account}:无条目({url})")
            continue
        count = 0
        for entry in parsed.entries:
            if count >= max_items_per_user:
                break
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            pub_dt = entry_published_at(entry)
            if not is_datetime_recent(pub_dt, max_age_days=max_age):
                continue
            posts.append(
                CommunityPost(
                    source=f"X·@{account}",
                    lane=lane,
                    title=title,
                    text=str(entry.get("summary") or "")[:400],
                    url=entry.get("link") or "",
                    published_at=pub_dt.isoformat() if pub_dt else "",
                    feed_key=f"twitter_{account}",
                )
            )
            count += 1
    return posts, errors


def fetch_all_twitter(cfg: dict[str, Any]) -> tuple[list[CommunityPost], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("community", {})
    if not ds.get("twitter", True):
        return [], [], []

    comm = cfg.get("community", {}) or {}
    base = str(comm.get("rsshub_base") or "https://rsshub.app").strip()
    accounts_cfg = comm.get("twitter_accounts") or DEFAULT_ACCOUNTS
    max_per = int(cfg.get("collector", {}).get("community_twitter_per_account", 8))

    all_posts: list[CommunityPost] = []
    summary: list[str] = []
    errors: list[str] = []

    for lane in ("btc", "eth", "sol"):
        accounts = accounts_cfg.get(lane) or DEFAULT_ACCOUNTS.get(lane, [])
        if not accounts:
            continue
        posts, errs = fetch_twitter_lane(
            lane, list(accounts), rsshub_base=base, max_items_per_user=max_per
        )
        all_posts.extend(posts)
        if posts:
            summary.append(f"X·{lane.upper()}：{len(posts)} 条")
        errors.extend(errs)

    if not all_posts and errors:
        summary.append("X：RSS 桥接暂不可用")
    return all_posts, summary, errors
