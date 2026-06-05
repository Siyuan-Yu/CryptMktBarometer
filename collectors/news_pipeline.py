"""
资讯采集后处理管线：车道隔离 → 质量筛选 → 分级计分修正。
"""

from __future__ import annotations

import logging
import re

from collectors.news_categories import (
    is_btc_related,
    is_eth_related,
    is_macro_related,
    is_sol_related,
    is_crypto_topic,
)
from collectors.news_impact_v2 import apply_tier_to_impact
from collectors.news_quality import apply_quality_pipeline, classify_news_tier
from collectors.news_recency import filter_recent_news
from collectors.news_source_catalog import CRYPTO_MACRO_FEED_KEYS
from collectors.news_source_keywords import (
    LANE_FEED_KEYS,
    filter_by_feed_keywords,
    matches_feed_keywords,
)
from collectors.types import NewsItem

logger = logging.getLogger(__name__)


def isolate_lane(items: list[NewsItem], lane: str) -> list[NewsItem]:
    """按车道剔除跨品类杂讯。"""
    if lane == "btc":
        out: list[NewsItem] = []
        for i in items:
            fk = (i.raw or {}).get("feed_key") or ""
            if fk in LANE_FEED_KEYS.get("btc", frozenset()):
                if matches_feed_keywords(i, fk, "btc"):
                    out.append(i)
                continue
            if is_btc_related(i) and not is_macro_related(i):
                out.append(i)
        return out
    if lane == "eth":
        out = []
        for i in items:
            fk = (i.raw or {}).get("feed_key") or ""
            if fk in LANE_FEED_KEYS.get("eth", frozenset()):
                if matches_feed_keywords(i, fk, "eth"):
                    out.append(i)
                continue
            if is_eth_related(i) and not is_btc_related(i, relaxed=True):
                out.append(i)
        return out
    if lane == "sol":
        out = []
        for i in items:
            fk = (i.raw or {}).get("feed_key") or ""
            if fk in LANE_FEED_KEYS.get("sol", frozenset()):
                if matches_feed_keywords(i, fk, "sol"):
                    out.append(i)
                continue
            if is_sol_related(i) and not is_btc_related(i, relaxed=True):
                out.append(i)
        return out
    if lane == "macro":
        out: list[NewsItem] = []
        for i in items:
            fk = (i.raw or {}).get("feed_key") or ""
            if fk in CRYPTO_MACRO_FEED_KEYS:
                if is_macro_related(i) or _reg_policy_topic(i):
                    out.append(i)
                continue
            if i.feed_type == "macro" and not is_crypto_topic(i) and is_macro_related(i):
                out.append(i)
        return out
    return list(items)


def _reg_policy_topic(item: NewsItem) -> bool:
    text = f"{item.title} {item.source}".lower()
    return bool(
        re.search(
            r"\b(sec|regulat|policy|etf|legislat|ban\b|approved|监管|法案|获批)\b",
            text,
            re.I,
        )
    )


def refresh_tiered_impact(items: list[NewsItem]) -> list[NewsItem]:
    for it in items:
        tier = classify_news_tier(it)
        it.impact_score = apply_tier_to_impact(it.impact_score, tier)
        it.logic = (it.logic or "") + f"；V2分级[{tier}]"
    return items


def process_lane_batch(items: list[NewsItem], lane: str) -> list[NewsItem]:
    isolated = isolate_lane(items, lane)
    keyed = filter_by_feed_keywords(isolated, lane)
    cleaned = apply_quality_pipeline(keyed)
    recent = filter_recent_news(cleaned)
    return refresh_tiered_impact(recent)


def merge_lane_batches(*batches: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for batch in batches:
        for it in batch:
            key = (it.url or it.title or "").strip().lower()[:200]
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(it)
    return out
