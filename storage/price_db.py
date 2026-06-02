"""
小时级价格数据库（SQLite）
保存 BTC / ETH / SOL 的 1h K 线，供消息冲击测算与回测使用。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from core.config_loader import PROJECT_ROOT, load_config

_SYMBOL_MAP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


def _db_path() -> Path:
    cfg = load_config()
    rel = cfg.get("weight_optimizer", {}).get("price_db", "data/market.db")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prices_hourly (
                symbol TEXT NOT NULL,
                ts INTEGER NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL,
                PRIMARY KEY (symbol, ts)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prices_ts ON prices_hourly(symbol, ts)"
        )
        conn.commit()


def upsert_candles(symbol: str, rows: Iterable[tuple]) -> int:
    """rows: (ts_ms, open, high, low, close, volume)"""
    sym = symbol.upper()
    n = 0
    with get_connection() as conn:
        for row in rows:
            ts_ms, o, h, l, c, v = row
            conn.execute(
                """
                INSERT INTO prices_hourly(symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, ts) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume
                """,
                (sym, int(ts_ms), o, h, l, c, v),
            )
            n += 1
        conn.commit()
    return n


def get_close_at(symbol: str, dt: datetime) -> float | None:
    """取不晚于 dt 的最近一根 K 线收盘价。"""
    sym = symbol.upper()
    ts_ms = int(dt.timestamp() * 1000)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT close FROM prices_hourly
            WHERE symbol=? AND ts<=?
            ORDER BY ts DESC LIMIT 1
            """,
            (sym, ts_ms),
        ).fetchone()
    return float(row["close"]) if row else None


def pct_change_after(symbol: str, start: datetime, hours: int) -> float | None:
    """从 start 时刻到 start+hours 的涨跌幅（%）。"""
    p0 = get_close_at(symbol, start)
    p1 = get_close_at(symbol, start + timedelta(hours=hours))
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (p1 - p0) / p0 * 100.0


def composite_pct_change(start: datetime, hours: int, symbols: list[str] | None = None) -> float | None:
    """多币种涨跌幅均值。"""
    syms = symbols or ["BTC", "ETH", "SOL"]
    vals = [pct_change_after(s, start, hours) for s in syms]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def count_candles(symbol: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM prices_hourly WHERE symbol=?",
            (symbol.upper(),),
        ).fetchone()
    return int(row["c"])


def symbol_to_pair(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol.upper(), f"{symbol.upper()}USDT")


def daily_close_series(
    symbol: str,
    start_date: str,
    end_date: str,
) -> dict[str, float]:
    """
    按 UTC 日聚合小时 K 线，取每日最后一根收盘价。
    返回 {YYYY-MM-DD: close}
    """
    init_schema()
    sym = symbol.upper()
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ts, close FROM prices_hourly
            WHERE symbol=? AND ts>=? AND ts<?
            ORDER BY ts ASC
            """,
            (sym, start_ms, end_ms),
        ).fetchall()

    daily: dict[str, float] = {}
    for row in rows:
        day = datetime.fromtimestamp(row["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        daily[day] = float(row["close"])
    return daily


def daily_return_series(
    symbol: str,
    start_date: str,
    end_date: str,
) -> dict[str, float]:
    """日收益率（%），键为日期。"""
    closes = daily_close_series(symbol, start_date, end_date)
    days = sorted(closes.keys())
    out: dict[str, float] = {}
    for i in range(1, len(days)):
        d = days[i]
        prev = closes[days[i - 1]]
        if prev:
            out[d] = (closes[d] - prev) / prev * 100.0
    return out
