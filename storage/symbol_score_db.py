"""
品种原始综合分历史（用于 90 天百分位 / min-max 归一化）。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
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
            CREATE TABLE IF NOT EXISTS symbol_raw_scores (
                fetch_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                raw_news REAL,
                raw_onchain REAL,
                raw_community REAL,
                raw_composite REAL NOT NULL,
                norm_score REAL,
                PRIMARY KEY (fetch_time, symbol)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_raw_sym_time "
            "ON symbol_raw_scores(symbol, fetch_time)"
        )
        conn.commit()


def insert_raw_score(
    fetch_time: str,
    symbol: str,
    *,
    raw_news: float,
    raw_onchain: float,
    raw_community: float,
    raw_composite: float,
    norm_score: float,
) -> None:
    init_schema()
    sym = symbol.upper()
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO symbol_raw_scores(
                fetch_time, symbol, raw_news, raw_onchain, raw_community,
                raw_composite, norm_score
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                fetch_time,
                sym,
                raw_news,
                raw_onchain,
                raw_community,
                raw_composite,
                norm_score,
            ),
        )
        conn.commit()


def get_raw_history(
    symbol: str,
    *,
    days: int = 90,
    before_time: str | None = None,
) -> list[float]:
    """取某品种近 N 天 raw_composite（不含当前点可选）。"""
    init_schema()
    sym = symbol.upper()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        SELECT raw_composite FROM symbol_raw_scores
        WHERE symbol = ? AND fetch_time >= ?
    """
    params: list = [sym, cutoff]
    if before_time:
        sql += " AND fetch_time < ?"
        params.append(before_time)
    sql += " ORDER BY fetch_time"
    with sqlite3.connect(_db_path()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def count_raw_history(symbol: str, *, days: int = 90) -> int:
    return len(get_raw_history(symbol, days=days))


def clear_scores_since(since: str) -> int:
    """删除 since 及之后的品种分数（全量重算前调用）。"""
    init_schema()
    since_dt = f"{since} 00:00:00"
    with sqlite3.connect(_db_path()) as conn:
        cur = conn.execute(
            "DELETE FROM symbol_raw_scores WHERE fetch_time >= ?",
            (since_dt,),
        )
        conn.commit()
        return cur.rowcount
