"""
资讯时效：展示与计分仅使用近期资讯（默认 3 天内，优先当日）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from collectors.types import NewsItem
from core.config_loader import load_config

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 3


def get_news_max_age_days(cfg: dict | None = None) -> int:
    collector = (cfg or load_config()).get("collector", {})
    try:
        days = int(collector.get("news_max_age_days", _DEFAULT_MAX_AGE_DAYS))
    except (TypeError, ValueError):
        days = _DEFAULT_MAX_AGE_DAYS
    return max(1, min(days, 14))


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_published_at(value: str | None) -> datetime | None:
    """解析 ISO / RSS 日期字符串为 UTC。"""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return _to_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return _to_utc(parsedate_to_datetime(raw))
    except Exception:
        return None


def entry_published_at(entry: dict[str, Any]) -> datetime | None:
    """从 feedparser entry 提取发布时间。"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(attr)
        if st:
            try:
                return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
            except Exception:
                continue
    for key in ("published", "updated", "created"):
        text = entry.get(key)
        if text:
            dt = parse_published_at(str(text))
            if dt:
                return dt
    return None


def news_item_age_days(item: NewsItem, *, now: datetime | None = None) -> float | None:
    now = _to_utc(now or datetime.now(timezone.utc))
    dt = parse_published_at(item.published_at)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def is_datetime_recent(
    dt: datetime | None,
    *,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> bool:
    if dt is None:
        return False
    max_age_days = max_age_days if max_age_days is not None else get_news_max_age_days()
    now = _to_utc(now or datetime.now(timezone.utc))
    age = max(0.0, (now - _to_utc(dt)).total_seconds() / 86400.0)
    return age <= float(max_age_days)


def is_recent_news(
    item: NewsItem,
    *,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> bool:
    """有发布时间且在 max_age_days 天内；无发布时间视为过期并剔除。"""
    dt = parse_published_at(item.published_at)
    return is_datetime_recent(dt, max_age_days=max_age_days, now=now)


def filter_recent_news(
    items: list[NewsItem],
    *,
    max_age_days: int | None = None,
    cfg: dict | None = None,
) -> list[NewsItem]:
    max_age_days = max_age_days if max_age_days is not None else get_news_max_age_days(cfg)
    now = datetime.now(timezone.utc)
    kept = [it for it in items if is_recent_news(it, max_age_days=max_age_days, now=now)]
    dropped = len(items) - len(kept)
    if dropped and items:
        logger.info(
            "资讯时效过滤：保留 %d 条，剔除 %d 条（超过 %d 天或无日期）",
            len(kept),
            dropped,
            max_age_days,
        )
    return kept


def recency_impact_sort_key(item: NewsItem, *, now: datetime | None = None) -> tuple:
    """
    排序：越新越靠前，同日内按 |impact| 降序。
    无日期排最后。
    """
    now = _to_utc(now or datetime.now(timezone.utc))
    age = news_item_age_days(item, now=now)
    if age is None:
        return (9999.0, 0.0)
    return (age, -abs(item.impact_score))


def sort_by_recency_impact(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=recency_impact_sort_key)
