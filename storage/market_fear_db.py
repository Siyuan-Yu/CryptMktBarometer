"""
大盘恐慌（alternative.me）每日历史 · 同自然日所有 4H 槽位复用。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from core.config_loader import PROJECT_ROOT, load_config


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
            CREATE TABLE IF NOT EXISTS market_fear_daily (
                trade_date TEXT PRIMARY KEY,
                value INTEGER NOT NULL,
                label_en TEXT,
                source TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def upsert_daily(
    trade_date: str,
    *,
    value: int,
    label_en: str = "",
    source: str = "alternative.me",
) -> None:
    init_schema()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO market_fear_daily(
                trade_date, value, label_en, source, updated_at
            ) VALUES (?,?,?,?,?)
            """,
            (trade_date, int(value), label_en, source, now),
        )
        conn.commit()


def get_daily(trade_date: str) -> dict | None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "SELECT trade_date, value, label_en, source FROM market_fear_daily WHERE trade_date=?",
            (trade_date,),
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row[0],
        "value": int(row[1]),
        "label_en": row[2] or "",
        "source": row[3] or "",
    }


def get_latest_before(trade_date: str) -> dict | None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            """
            SELECT trade_date, value, label_en, source
            FROM market_fear_daily WHERE trade_date<=?
            ORDER BY trade_date DESC LIMIT 1
            """,
            (trade_date,),
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row[0],
        "value": int(row[1]),
        "label_en": row[2] or "",
        "source": row[3] or "",
    }


def get_market_fear_for_slot(at: datetime) -> dict:
    day = at.strftime("%Y-%m-%d")
    row = get_daily(day) or get_latest_before(day)
    if not row:
        return {"value": None, "trade_date": day, "source": "none"}
    return row
