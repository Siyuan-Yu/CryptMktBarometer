"""
单币种每日恐慌系数（CFGI / 代理）· 按自然日对齐 4H K 线。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from core.config_loader import PROJECT_ROOT, load_config

_SYMBOLS = ("BTC", "ETH", "SOL")


def _db_path() -> Path:
    cfg = load_config()
    rel = cfg.get("weight_optimizer", {}).get("price_db", "data/market.db")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_schema() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coin_fear_daily (
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                value INTEGER NOT NULL,
                label TEXT,
                source TEXT,
                updated_at TEXT,
                PRIMARY KEY (trade_date, symbol)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_coin_fear_sym_date "
            "ON coin_fear_daily(symbol, trade_date)"
        )
        conn.commit()


def upsert_daily(
    trade_date: str,
    symbol: str,
    *,
    value: int,
    label: str = "",
    source: str = "cfgi",
) -> None:
    init_schema()
    sym = symbol.upper()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO coin_fear_daily(
                trade_date, symbol, value, label, source, updated_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (trade_date, sym, int(value), label, source, now),
        )
        conn.commit()


def get_daily(
    symbol: str,
    trade_date: str,
) -> dict | None:
    init_schema()
    sym = symbol.upper()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            """
            SELECT trade_date, symbol, value, label, source, updated_at
            FROM coin_fear_daily
            WHERE symbol=? AND trade_date=?
            """,
            (sym, trade_date),
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row[0],
        "symbol": row[1],
        "value": int(row[2]),
        "label": row[3] or "",
        "source": row[4] or "",
        "updated_at": row[5] or "",
    }


def get_latest_before(
    symbol: str,
    trade_date: str,
) -> dict | None:
    """取不晚于 trade_date 的最近一条（前一日缓存容错）。"""
    init_schema()
    sym = symbol.upper()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            """
            SELECT trade_date, symbol, value, label, source, updated_at
            FROM coin_fear_daily
            WHERE symbol=? AND trade_date<=?
            ORDER BY trade_date DESC LIMIT 1
            """,
            (sym, trade_date),
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row[0],
        "symbol": row[1],
        "value": int(row[2]),
        "label": row[3] or "",
        "source": row[4] or "",
        "updated_at": row[5] or "",
    }


def get_coin_fear_for_slot(symbol: str, at: datetime) -> dict:
    """4H 槽位使用当日自然日恐慌；失败回退前一日。"""
    day = at.strftime("%Y-%m-%d")
    row = get_daily(symbol, day) or get_latest_before(symbol, day)
    if not row:
        return {
            "value": None,
            "label": "—",
            "zone": "fg-unknown",
            "trade_date": day,
            "source": "none",
        }
    from scoring.coin_fear import classify_coin_fear

    zone, label = classify_coin_fear(row["value"])
    return {
        "value": row["value"],
        "label": label,
        "zone": zone,
        "trade_date": row["trade_date"],
        "source": row["source"],
    }


def get_all_latest() -> dict[str, dict]:
    """三币种最新可用日恐慌（供 /api/prices）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    out: dict[str, dict] = {}
    for sym in _SYMBOLS:
        row = get_daily(sym, today) or get_latest_before(sym, today)
        if not row:
            out[sym] = {"value": None, "label": "—", "zone": "fg-unknown"}
            continue
        from scoring.coin_fear import classify_coin_fear

        zone, label = classify_coin_fear(row["value"])
        out[sym] = {
            "value": row["value"],
            "label": label,
            "zone": zone,
            "trade_date": row["trade_date"],
            "source": row["source"],
        }
    return out


def iter_dates(symbol: str, start: str, end: str) -> list[dict]:
    init_schema()
    sym = symbol.upper()
    with sqlite3.connect(_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT trade_date, value, label, source
            FROM coin_fear_daily
            WHERE symbol=? AND trade_date>=? AND trade_date<=?
            ORDER BY trade_date
            """,
            (sym, start, end),
        ).fetchall()
    return [
        {
            "trade_date": r[0],
            "value": int(r[1]),
            "label": r[2] or "",
            "source": r[3] or "",
        }
        for r in rows
    ]
