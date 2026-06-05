"""
社区舆情快照（SQLite，market.db 新表，不改既有表）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from collectors.community_sentiment import LaneSentiment
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
            CREATE TABLE IF NOT EXISTS community_snapshots (
                fetched_at TEXT PRIMARY KEY,
                market_impact REAL,
                btc_impact REAL,
                eth_impact REAL,
                sol_impact REAL,
                btc_bull_pct REAL,
                eth_bull_pct REAL,
                sol_bull_pct REAL,
                payload_json TEXT
            )
            """
        )
        conn.commit()


def insert_community_snapshot(
    fetched_at: str,
    lanes: dict[str, LaneSentiment],
    market_impact: float,
    payload: str,
) -> None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO community_snapshots(
                fetched_at, market_impact,
                btc_impact, eth_impact, sol_impact,
                btc_bull_pct, eth_bull_pct, sol_bull_pct,
                payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                fetched_at,
                market_impact,
                lanes.get("btc", LaneSentiment("btc")).aggregate_impact,
                lanes.get("eth", LaneSentiment("eth")).aggregate_impact,
                lanes.get("sol", LaneSentiment("sol")).aggregate_impact,
                lanes.get("btc", LaneSentiment("btc")).bullish_pct,
                lanes.get("eth", LaneSentiment("eth")).bullish_pct,
                lanes.get("sol", LaneSentiment("sol")).bullish_pct,
                payload[:8000],
            ),
        )
        conn.commit()


def load_latest_snapshot() -> dict[str, LaneSentiment] | None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "SELECT * FROM community_snapshots ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    lanes = {}
    for lane, idx_impact, idx_pct in (
        ("btc", 2, 5),
        ("eth", 3, 6),
        ("sol", 4, 7),
    ):
        lanes[lane] = LaneSentiment(
            lane=lane,
            aggregate_impact=float(row[idx_impact] or 0),
            bullish_pct=float(row[idx_pct] or 50),
            summary=f"缓存·多{row[idx_pct]:.0f}%",
        )
    return lanes


def last_community_age_hours() -> float | None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "SELECT fetched_at FROM community_snapshots ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    try:
        ts = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    except ValueError:
        return None
