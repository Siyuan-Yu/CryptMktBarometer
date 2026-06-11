"""
大盘恐慌（alternative.me）同步与历史回填。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from collectors.onchain_apis import fetch_fear_greed
from collectors.http_client import fetch_json
from core.config_loader import load_config
from storage.market_fear_db import get_latest_before, upsert_daily

logger = logging.getLogger(__name__)


def fetch_alternative_me_history(*, limit: int = 2000) -> list[dict]:
    """拉取 alternative.me 日频历史。"""
    cfg = load_config()
    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))
    data = fetch_json(
        "https://api.alternative.me/fng/",
        params={"limit": limit},
        timeout=timeout,
    )
    seen: set[str] = set()
    out: list[dict] = []
    for row in data.get("data") or []:
        try:
            ts = int(row.get("timestamp", 0))
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if day in seen:
                continue
            seen.add(day)
            out.append(
                {
                    "trade_date": day,
                    "value": int(row.get("value", 0)),
                    "label_en": str(row.get("value_classification") or ""),
                }
            )
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda r: r["trade_date"])
    return out


def sync_today() -> dict | None:
    """写入今日大盘恐慌；失败沿用昨日缓存。"""
    today = datetime.now().strftime("%Y-%m-%d")
    val, label_en, err = fetch_fear_greed()
    if val is not None:
        upsert_daily(today, value=val, label_en=label_en)
        return {"value": val, "label_en": label_en, "trade_date": today, "source": "alternative.me"}
    prev = get_latest_before(today)
    if prev:
        logger.info("大盘恐慌使用缓存 %s", prev["trade_date"])
        return {
            "value": prev["value"],
            "label_en": prev.get("label_en", ""),
            "trade_date": prev["trade_date"],
            "source": f"cache:{prev['trade_date']}",
        }
    logger.warning("大盘恐慌拉取失败: %s", err)
    return None


def backfill_range(*, start_date: str, end_date: str) -> int:
    rows = fetch_alternative_me_history(limit=2500)
    n = 0
    for row in rows:
        d = row["trade_date"]
        if d < start_date or d > end_date:
            continue
        upsert_daily(
            d,
            value=row["value"],
            label_en=row.get("label_en", ""),
        )
        n += 1
    if n == 0:
        sync_today()
        return 1
    return n
