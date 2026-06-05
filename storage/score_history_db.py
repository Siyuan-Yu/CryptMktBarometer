"""
score_history_4h 表读写：供折线图 API 快速读取，避免逐行重算 ETH/SOL。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from core.config_loader import PROJECT_ROOT, load_config
from scoring.multi_asset import signal_from_score


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
            CREATE TABLE IF NOT EXISTS score_history_4h (
                fetch_time TEXT PRIMARY KEY,
                total_score REAL NOT NULL,
                rating TEXT,
                macro REAL,
                regulation REAL,
                funding REAL,
                fundamentals REAL,
                btc_score REAL,
                eth_score REAL,
                sol_score REAL,
                us_score REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_score_hist_4h_time "
            "ON score_history_4h(fetch_time)"
        )
        conn.commit()


def _bucket_4h(dt: datetime) -> datetime:
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def upsert_4h_scores(
    fetch_time: datetime,
    *,
    norm_scores: dict[str, float],
    rating: str,
    macro: float | None = None,
    regulation: float | None = None,
    funding: float | None = None,
    fundamentals: float | None = None,
    us_score: float | None = None,
) -> None:
    """将本轮归一化分写入 4h 桶（同桶覆盖）。"""
    init_schema()
    bucket = _bucket_4h(fetch_time)
    ts = bucket.strftime("%Y-%m-%d %H:%M:%S")
    btc = float(norm_scores.get("BTC", norm_scores.get("btc", 50)))
    eth = float(norm_scores.get("ETH", norm_scores.get("eth", 50)))
    sol = float(norm_scores.get("SOL", norm_scores.get("sol", 50)))
    us = us_score if us_score is not None else btc

    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO score_history_4h(
                fetch_time, total_score, rating,
                macro, regulation, funding, fundamentals,
                btc_score, eth_score, sol_score, us_score
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ts,
                btc,
                rating,
                macro,
                regulation,
                funding,
                fundamentals,
                btc,
                eth,
                sol,
                us,
            ),
        )
        conn.commit()


def read_4h_series(*, since: str = "2025-01-01") -> dict[str, list[dict]]:
    """读取四品种 4h 历史序列。"""
    init_schema()
    since_dt = f"{since} 00:00:00"
    out: dict[str, list[dict]] = {
        "btc": [],
        "eth": [],
        "sol": [],
        "us": [],
    }
    with sqlite3.connect(_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT fetch_time, rating, btc_score, eth_score, sol_score, us_score
            FROM score_history_4h
            WHERE fetch_time >= ?
            ORDER BY fetch_time
            """,
            (since_dt,),
        ).fetchall()

    for fetch_time, rating, btc, eth, sol, us in rows:
        base = {"time": fetch_time, "rating": rating or ""}
        mapping = (
            ("btc", btc),
            ("eth", eth),
            ("sol", sol),
            ("us", us),
        )
        for key, score in mapping:
            if score is None:
                continue
            s = round(float(score), 1)
            out[key].append(
                {
                    **base,
                    "score": s,
                    "signal": signal_from_score(s),
                }
            )
    return out


def latest_4h_time() -> str | None:
    init_schema()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "SELECT MAX(fetch_time) FROM score_history_4h"
        ).fetchone()
    return row[0] if row and row[0] else None
