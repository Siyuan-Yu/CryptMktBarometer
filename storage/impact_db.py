"""
消息-价格冲击记录库
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config_loader import PROJECT_ROOT, load_config


def _db_path() -> Path:
    cfg = load_config()
    rel = cfg.get("weight_optimizer", {}).get("impact_db", "data/market.db")
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
            CREATE TABLE IF NOT EXISTS news_impacts (
                id TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                url TEXT,
                module TEXT NOT NULL,
                published_at TEXT NOT NULL,
                predicted_impact REAL,
                actual_1h REAL,
                actual_4h REAL,
                actual_24h REAL,
                composite_24h REAL,
                is_event INTEGER DEFAULT 0,
                recorded_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_impact_pub ON news_impacts(published_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_impact_mod ON news_impacts(module)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weight_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                macro INTEGER, regulation INTEGER, funding INTEGER, fundamentals INTEGER,
                method TEXT, updated_at TEXT, next_recalc_at TEXT
            )
            """
        )
        conn.commit()


def _news_id(title: str, url: str, published_at: str) -> str:
    raw = f"{title}|{url}|{published_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def insert_news_pending(
    *,
    title: str,
    source: str,
    url: str,
    module: str,
    published_at: datetime,
    predicted_impact: float,
    is_event: bool = False,
) -> str:
    init_schema()
    nid = _news_id(title, url, published_at.isoformat())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO news_impacts(
                id, title, source, url, module, published_at,
                predicted_impact, is_event, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                nid,
                title[:500],
                source,
                url,
                module,
                published_at.isoformat(),
                predicted_impact,
                1 if is_event else 0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    return nid


def update_actual_impacts(
    news_id: str,
    *,
    actual_1h: float | None,
    actual_4h: float | None,
    actual_24h: float | None,
    composite_24h: float | None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE news_impacts SET
                actual_1h=?, actual_4h=?, actual_24h=?, composite_24h=?
            WHERE id=?
            """,
            (actual_1h, actual_4h, actual_24h, composite_24h, news_id),
        )
        conn.commit()


def list_pending_measurement(before: datetime | None = None) -> list[sqlite3.Row]:
    """需要补全实际冲击的消息（24h 字段为空）。"""
    init_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM news_impacts
            WHERE composite_24h IS NULL
            ORDER BY published_at ASC
            """
        ).fetchall()
    return list(rows)


def list_impacts_between(start: str, end: str) -> list[dict[str, Any]]:
    init_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM news_impacts
            WHERE published_at >= ? AND published_at <= ?
            AND composite_24h IS NOT NULL
            ORDER BY published_at
            """,
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def module_influence_stats(days: int) -> dict[str, dict[str, float]]:
    """最近 N 天各模块影响力（平均绝对冲击、加权冲击）。"""
    init_schema()
    since = (datetime.now() - __import__("datetime").timedelta(days=days)).isoformat()
    modules = ("macro", "regulation", "funding", "fundamentals")
    out: dict[str, dict[str, float]] = {m: {"abs_avg": 0.0, "signed_avg": 0.0, "count": 0} for m in modules}
    with get_connection() as conn:
        for mod in modules:
            rows = conn.execute(
                """
                SELECT composite_24h, predicted_impact, is_event FROM news_impacts
                WHERE module=? AND published_at>=? AND composite_24h IS NOT NULL
                """,
                (mod, since),
            ).fetchall()
            if not rows:
                continue
            abs_vals = [abs(float(r["composite_24h"])) for r in rows]
            signed = [float(r["composite_24h"]) for r in rows]
            out[mod] = {
                "abs_avg": sum(abs_vals) / len(abs_vals),
                "signed_avg": sum(signed) / len(signed),
                "count": float(len(rows)),
                "event_ratio": sum(int(r["is_event"]) for r in rows) / len(rows),
            }
    return out


def count_measured_impacts() -> int:
    init_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM news_impacts WHERE composite_24h IS NOT NULL"
        ).fetchone()
    return int(row["c"])


def count_total_impacts() -> int:
    init_schema()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM news_impacts").fetchone()
    return int(row["c"])


def save_weight_state(
    macro: int,
    regulation: int,
    funding: int,
    fundamentals: int,
    *,
    method: str,
    next_recalc_at: str,
) -> None:
    init_schema()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM weight_state WHERE id=1")
        conn.execute(
            """
            INSERT INTO weight_state(id, macro, regulation, funding, fundamentals, method, updated_at, next_recalc_at)
            VALUES (1,?,?,?,?,?,?,?)
            """,
            (macro, regulation, funding, fundamentals, method, now, next_recalc_at),
        )
        conn.commit()


def load_weight_state() -> dict[str, Any] | None:
    init_schema()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM weight_state WHERE id=1").fetchone()
    return dict(row) if row else None


def has_recent_event(module: str, hours: int = 24) -> bool:
    """该模块在 past N 小时内是否有突发事件标记（CPI/美联储/ETF/SEC/爆仓等）。"""
    init_schema()
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM news_impacts
            WHERE module=? AND is_event=1 AND published_at>=?
            LIMIT 1
            """,
            (module, since),
        ).fetchone()
    return row is not None


def module_idle_days(module: str, days: int = 30, threshold: float = 0.2) -> bool:
    """最近 N 天几乎无有效冲击。"""
    stats = module_influence_stats(days).get(module, {})
    return float(stats.get("count", 0)) < 1 or float(stats.get("abs_avg", 0)) < threshold


def recent_weak_streak(module: str, threshold: float = 0.3, streak: int = 3) -> bool:
    """连续 N 次冲击很小。"""
    init_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT composite_24h FROM news_impacts
            WHERE module=? AND composite_24h IS NOT NULL
            ORDER BY published_at DESC LIMIT ?
            """,
            (module, streak),
        ).fetchall()
    if len(rows) < streak:
        return False
    return all(abs(float(r["composite_24h"])) < threshold for r in rows)
