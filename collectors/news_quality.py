"""
资讯质量筛选、分级、4 小时去重。
标签写入 NewsItem.raw，不新增数据库列。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from collectors.news_source_catalog import PREMIUM_AUTHORITY_FEED_KEYS
from collectors.types import NewsItem

# 小道消息 / 低质量源特征
_RUMOR_SOURCES = re.compile(
    r"twitter|reddit|telegram|medium\.com|substack|匿名|据传|消息人士|"
    r"unverified|rumor|传闻|爆料",
    re.I,
)

_RUMOR_TITLE = re.compile(
    r"^(just in|breaking(?!\s+news)|🚨|⚡|rumor|alleged| reportedly)\b",
    re.I,
)

# 重磅：官方 / ETF / 升级 / 政策
_MAJOR_PATTERNS = re.compile(
    r"\b(etf approved|spot etf|etf launch|rate decision|fomc|halving|"
    r"mainnet upgrade|hard fork|foundation announces|sec approves|"
    r"official announcement|cpi report|nonfarm payroll|fed raises|fed cuts|"
    r"获批|通过审查|正式上线|重大升级|黑客攻击|exploit|破产|"
    r"减半|现货etf|议息|非农|灰度|gbtc)\b",
    re.I,
)

_OFFICIAL_TIERS = frozenset({"official", "authority", "research"})

_MIN_TITLE_LEN = 12
_MIN_BODY_HINT_LEN = 0


def detect_source_tier(item: NewsItem) -> str:
    raw = item.raw or {}
    tier = raw.get("source_tier") or "aggregate"
    if tier in _OFFICIAL_TIERS:
        return tier
    src = (item.source or "").lower()
    if any(
        k in src
        for k in (
            "sec",
            "fed",
            "foundation",
            "bls",
            "reuters",
            "cnbc",
            "glassnode",
            "grayscale",
            "ark",
            "bankless",
            "defiant",
            "blockworks",
            "decrypt",
            "marinade",
            "jupiter",
            "magicians",
            "optimism",
            "arbitrum",
            "bitcoin core",
            "bitcoin magazine",
        )
    ):
        return "authority"
    return "aggregate"


def classify_news_tier(item: NewsItem) -> str:
    """major | normal | rumor"""
    text = f"{item.title} {item.logic}".lower()
    feed_key = (item.raw or {}).get("feed_key") or ""
    src_tier = detect_source_tier(item)
    if _RUMOR_SOURCES.search(item.source) or _RUMOR_TITLE.search(item.title):
        return "rumor"
    if feed_key in PREMIUM_AUTHORITY_FEED_KEYS and src_tier in _OFFICIAL_TIERS:
        return "major"
    if src_tier in _OFFICIAL_TIERS and _MAJOR_PATTERNS.search(text):
        return "major"
    if _MAJOR_PATTERNS.search(text):
        return "major"
    if src_tier == "aggregate" and not _MAJOR_PATTERNS.search(text):
        return "rumor"
    return "normal"


def is_quality_item(item: NewsItem) -> bool:
    title = (item.title or "").strip()
    if len(title) < _MIN_TITLE_LEN:
        return False
    if _RUMOR_SOURCES.search(item.source) and classify_news_tier(item) == "rumor":
        return False
    # 剔除明显水文
    if len(title) < 20 and title.lower().startswith(("click", "read more", "watch")):
        return False
    return True


def _parse_published(item: NewsItem) -> datetime:
    raw = (item.published_at or "").strip()
    if not raw:
        return datetime.now()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now()


def _bucket_4h(dt: datetime) -> datetime:
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def _event_fingerprint(item: NewsItem) -> str:
    """同源同事件去重指纹。"""
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (item.title or "").lower())
    words = [w for w in text.split() if len(w) > 2][:8]
    base = " ".join(sorted(set(words)))
    src = (item.source or "").split("·")[0].strip().lower()
    lane = (item.raw or {}).get("asset_lane", "")
    return hashlib.sha256(f"{src}|{lane}|{base}".encode()).hexdigest()[:16]


def dedupe_4h(items: list[NewsItem]) -> list[NewsItem]:
    """4 小时内同源同事件仅保留影响分绝对值最高的一条。"""
    buckets: dict[tuple[str, str], NewsItem] = {}

    for item in items:
        pub = _bucket_4h(_parse_published(item))
        fp = _event_fingerprint(item)
        key = (pub.isoformat(), fp)
        prev = buckets.get(key)
        if prev is None or abs(item.impact_score) > abs(prev.impact_score):
            buckets[key] = item

    out = list(buckets.values())
    out.sort(key=lambda x: abs(x.impact_score), reverse=True)
    return out


def enrich_item_metadata(item: NewsItem) -> NewsItem:
    raw: dict[str, Any] = dict(item.raw or {})
    lane = raw.get("asset_lane", "")
    tier = classify_news_tier(item)
    src_tier = detect_source_tier(item)
    raw["news_tier"] = tier
    raw["source_tier"] = src_tier
    raw["source_tag"] = f"{lane or item.feed_type}|{src_tier}|{tier}"
    item.raw = raw
    return item


def apply_quality_pipeline(items: list[NewsItem]) -> list[NewsItem]:
    filtered = [enrich_item_metadata(it) for it in items if is_quality_item(it)]
    return dedupe_4h(filtered)
