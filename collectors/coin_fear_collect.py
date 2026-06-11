"""
同步 BTC/ETH/SOL 每日币种恐慌（多源抽象层 → DB，失败用前日缓存或价格代理）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from collectors.coin_fear_providers import (
    SYMBOLS,
    fetch_history_primary,
    resolve_coin_fear_value,
)
from collectors.coin_fear_proxy import proxy_coin_fear_for_date
from scoring.coin_fear import classify_coin_fear
from storage.coin_fear_db import get_latest_before, upsert_daily

logger = logging.getLogger(__name__)

_last_sync_day: str | None = None


def sync_today(*, force: bool = False) -> dict[str, dict]:
    """写入今日三币种恐慌（自然日仅同步一次，除非 force）。"""
    global _last_sync_day
    today = datetime.now().strftime("%Y-%m-%d")
    if not force and _last_sync_day == today:
        from storage.coin_fear_db import get_all_latest

        return get_all_latest()
    out: dict[str, dict] = {}
    for sym in SYMBOLS:
        try:
            val, source = resolve_coin_fear_value(sym, today)
            zone, label = classify_coin_fear(val)
            upsert_daily(today, sym, value=val, label=label, source=source)
            out[sym] = {
                "value": val,
                "label": label,
                "zone": zone,
                "trade_date": today,
                "source": source,
            }
        except Exception as exc:
            logger.warning("sync_today %s failed: %s", sym, exc)
            prev = get_latest_before(sym, today)
            if prev:
                zone, label = classify_coin_fear(prev["value"])
                out[sym] = {
                    "value": prev["value"],
                    "label": label,
                    "zone": zone,
                    "trade_date": prev["trade_date"],
                    "source": prev.get("source", "cache"),
                }
    _last_sync_day = today
    return out


def backfill_daily_range(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
) -> int:
    """全量回填自然日恐慌（主源 CFGI，失败走价格代理）。"""
    sym = symbol.upper()
    samples = fetch_history_primary(
        sym, start_date=start_date, end_date=end_date
    )
    n = 0
    if samples:
        for sample in samples:
            zone, label = classify_coin_fear(sample.value)
            upsert_daily(
                sample.trade_date or start_date,
                sym,
                value=sample.value,
                label=label,
                source=sample.source,
            )
            n += 1
        return n

    logger.info("CFGI history empty for %s, use price proxy", sym)
    cur = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while cur <= end:
        day = cur.strftime("%Y-%m-%d")
        val = proxy_coin_fear_for_date(sym, day)
        zone, label = classify_coin_fear(val)
        upsert_daily(day, sym, value=val, label=label, source="proxy")
        n += 1
        cur += timedelta(days=1)
    return n
