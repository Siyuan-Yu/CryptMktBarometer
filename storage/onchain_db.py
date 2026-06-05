"""
链上客观指标快照（SQLite，与 market.db 同库，新增表不改既有表结构）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config_loader import PROJECT_ROOT, load_config


@dataclass
class OnchainSnapshot:
    fetched_at: str
    fear_greed: int | None = None
    fear_greed_class: str = ""
    btc_hashrate_chg_pct: float | None = None
    eth_volume_24h_usd: float | None = None
    eth_largest_tx_24h_usd: float | None = None
    sol_tvl_chg_pct: float | None = None
    market_cap_chg_24h_pct: float | None = None
    volume_chg_24h_pct: float | None = None
    etf_flow_proxy_pct: float | None = None
    adj_market: float = 0.0
    adj_btc: float = 0.0
    adj_eth: float = 0.0
    adj_sol: float = 0.0
    summary: str = ""
    raw_json: str = ""
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


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
            CREATE TABLE IF NOT EXISTS onchain_snapshots (
                fetched_at TEXT PRIMARY KEY,
                fear_greed INTEGER,
                fear_greed_class TEXT,
                btc_hashrate_chg_pct REAL,
                eth_volume_24h_usd REAL,
                eth_largest_tx_24h_usd REAL,
                sol_tvl_chg_pct REAL,
                market_cap_chg_24h_pct REAL,
                volume_chg_24h_pct REAL,
                etf_flow_proxy_pct REAL,
                adj_market REAL,
                adj_btc REAL,
                adj_eth REAL,
                adj_sol REAL,
                summary TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_onchain_time ON onchain_snapshots(fetched_at)"
        )
        conn.commit()


def insert_snapshot(snap: OnchainSnapshot) -> None:
    init_schema()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO onchain_snapshots(
                fetched_at, fear_greed, fear_greed_class,
                btc_hashrate_chg_pct, eth_volume_24h_usd, eth_largest_tx_24h_usd,
                sol_tvl_chg_pct, market_cap_chg_24h_pct, volume_chg_24h_pct,
                etf_flow_proxy_pct, adj_market, adj_btc, adj_eth, adj_sol,
                summary, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                snap.fetched_at,
                snap.fear_greed,
                snap.fear_greed_class,
                snap.btc_hashrate_chg_pct,
                snap.eth_volume_24h_usd,
                snap.eth_largest_tx_24h_usd,
                snap.sol_tvl_chg_pct,
                snap.market_cap_chg_24h_pct,
                snap.volume_chg_24h_pct,
                snap.etf_flow_proxy_pct,
                snap.adj_market,
                snap.adj_btc,
                snap.adj_eth,
                snap.adj_sol,
                snap.summary,
                snap.raw_json,
            ),
        )
        conn.commit()


def get_latest_snapshot() -> OnchainSnapshot | None:
    init_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM onchain_snapshots ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return _row_to_snap(row)


def get_previous_snapshot(before_iso: str) -> OnchainSnapshot | None:
    init_schema()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM onchain_snapshots
            WHERE fetched_at < ?
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (before_iso,),
        ).fetchone()
    if not row:
        return None
    return _row_to_snap(row)


def _row_to_snap(row: sqlite3.Row) -> OnchainSnapshot:
    return OnchainSnapshot(
        fetched_at=row["fetched_at"],
        fear_greed=row["fear_greed"],
        fear_greed_class=row["fear_greed_class"] or "",
        btc_hashrate_chg_pct=row["btc_hashrate_chg_pct"],
        eth_volume_24h_usd=row["eth_volume_24h_usd"],
        eth_largest_tx_24h_usd=row["eth_largest_tx_24h_usd"],
        sol_tvl_chg_pct=row["sol_tvl_chg_pct"],
        market_cap_chg_24h_pct=row["market_cap_chg_24h_pct"],
        volume_chg_24h_pct=row["volume_chg_24h_pct"],
        etf_flow_proxy_pct=row["etf_flow_proxy_pct"],
        adj_market=row["adj_market"] or 0.0,
        adj_btc=row["adj_btc"] or 0.0,
        adj_eth=row["adj_eth"] or 0.0,
        adj_sol=row["adj_sol"] or 0.0,
        summary=row["summary"] or "",
        raw_json=row["raw_json"] or "",
    )


def last_fetch_age_hours() -> float | None:
    snap = get_latest_snapshot()
    if not snap or not snap.fetched_at:
        return None
    try:
        ts = datetime.fromisoformat(snap.fetched_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - ts).total_seconds() / 3600.0
    except ValueError:
        return None
