"""
小时 K 线抓取（Binance 公开接口，无需 API Key）
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from storage.price_db import init_schema, symbol_to_pair, upsert_candles

logger = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"


def fetch_klines_batch(
    symbol: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
    timeout: int = 20,
) -> list[tuple]:
    pair = symbol_to_pair(symbol)
    params: dict = {"symbol": pair, "interval": "1h", "limit": limit}
    if start_ms:
        params["startTime"] = start_ms
    if end_ms:
        params["endTime"] = end_ms
    resp = requests.get(
        BINANCE_KLINES,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "CryptMktBarometer/1.0"},
    )
    resp.raise_for_status()
    data = resp.json()
    rows = []
    for k in data:
        rows.append((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))
    return rows


def sync_recent_hours(symbols: list[str], hours: int = 168) -> dict[str, int]:
    """拉取最近 N 小时 K 线并入库。"""
    init_schema()
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    start_ms = int(start.timestamp() * 1000)
    counts: dict[str, int] = {}
    for sym in symbols:
        try:
            rows = fetch_klines_batch(sym, start_ms=start_ms, limit=min(hours + 2, 1000))
            counts[sym] = upsert_candles(sym, rows)
            logger.info("%s 同步 %d 根小时K线", sym, counts[sym])
        except Exception as exc:
            logger.warning("%s K线同步失败: %s", sym, exc)
            counts[sym] = 0
        time.sleep(0.2)
    return counts


def backfill_history(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    """
    回填历史小时 K 线（用于回测）。
    日期格式 YYYY-MM-DD
    """
    init_schema()
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    total: dict[str, int] = {s: 0 for s in symbols}

    for sym in symbols:
        cursor = start_dt
        while cursor < end_dt:
            start_ms = int(cursor.timestamp() * 1000)
            end_ms = int(min(cursor + timedelta(hours=999), end_dt).timestamp() * 1000)
            try:
                rows = fetch_klines_batch(sym, start_ms=start_ms, end_ms=end_ms, limit=1000)
                total[sym] += upsert_candles(sym, rows)
            except Exception as exc:
                logger.warning("%s 回填失败 @ %s: %s", sym, cursor.date(), exc)
            cursor += timedelta(hours=999)
            time.sleep(0.25)
        logger.info("%s 历史回填合计 %d 根", sym, total[sym])
    return total
