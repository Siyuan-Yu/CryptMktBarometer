"""
历史 4h 回测：由小时 K 线推导链上/资金客观因子代理（成交量、合约动量、巨鲸异动）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from scoring.multi_asset import _pct_at
from scoring.onchain_objective import compute_adjustments
from scoring.utils import clamp
from storage import price_db
from storage.onchain_db import OnchainSnapshot


def _sum_volume(symbol: str, end: datetime, hours: int) -> float | None:
    sym = symbol.upper()
    end_ms = int(end.timestamp() * 1000)
    start_ms = int((end - timedelta(hours=hours)).timestamp() * 1000)
    with price_db.get_connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(volume), 0) AS v FROM prices_hourly
            WHERE symbol=? AND ts>? AND ts<=?
            """,
            (sym, start_ms, end_ms),
        ).fetchone()
    if not row or row["v"] is None:
        return None
    return float(row["v"])


def _volume_change_pct(symbol: str, at: datetime, hours: int = 24) -> float | None:
    v1 = _sum_volume(symbol, at, hours)
    v0 = _sum_volume(symbol, at - timedelta(hours=hours), hours)
    if v1 is None or v0 is None or v0 <= 0:
        return None
    return (v1 - v0) / v0 * 100.0


def _max_intrabar_notional_usd(symbol: str, at: datetime, hours: int = 24) -> float | None:
    """巨鲸/大额异动代理：窗口内单小时 (high-low)*close 最大值。"""
    sym = symbol.upper()
    end_ms = int(at.timestamp() * 1000)
    start_ms = int((at - timedelta(hours=hours)).timestamp() * 1000)
    with price_db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT high, low, close FROM prices_hourly
            WHERE symbol=? AND ts>? AND ts<=?
            """,
            (sym, start_ms, end_ms),
        ).fetchall()
    if not rows:
        return None
    best = 0.0
    for r in rows:
        h, l, c = float(r["high"]), float(r["low"]), float(r["close"])
        if c > 0 and h >= l:
            best = max(best, (h - l) * c)
    return best if best > 0 else None


def build_onchain_proxy_at(at: datetime) -> OnchainSnapshot:
    """由价格/成交量/波动构造链上快照并计算 adj_*。"""
    btc_24 = _pct_at("BTC", at, 0, 24) or 0.0
    btc_4 = _pct_at("BTC", at, 0, 4) or 0.0
    eth_24 = _pct_at("ETH", at, 0, 24) or 0.0
    sol_24 = _pct_at("SOL", at, 0, 24) or 0.0
    eth_4 = _pct_at("ETH", at, 0, 4) or 0.0

    vol_chg = _volume_change_pct("BTC", at, 24)
    eth_vol_chg = _volume_change_pct("ETH", at, 24)
    whale_usd = _max_intrabar_notional_usd("ETH", at, 24)

    fg = int(clamp(50.0 - btc_24 * 4.0, 8.0, 92.0))
    fg_class = (
        "Extreme Fear"
        if fg < 25
        else "Fear"
        if fg < 45
        else "Greed"
        if fg > 55
        else "Neutral"
    )

    snap = OnchainSnapshot(
        fetched_at=at.strftime("%Y-%m-%d %H:%M:%S"),
        fear_greed=fg,
        fear_greed_class=fg_class,
        btc_hashrate_chg_pct=round(btc_4 * 1.2, 2),
        eth_volume_24h_usd=5e9 if eth_vol_chg is None else 5e9 * (1 + eth_vol_chg / 100),
        eth_largest_tx_24h_usd=whale_usd,
        sol_tvl_chg_pct=round(sol_24 * 0.6, 2),
        market_cap_chg_24h_pct=round(btc_24, 2),
        volume_chg_24h_pct=round(vol_chg, 2) if vol_chg is not None else None,
        etf_flow_proxy_pct=round(btc_24, 2),
    )

    adj = compute_adjustments(snap)
    contract_bias = clamp(eth_4 * 0.35 + btc_4 * 0.25, -4.0, 4.0)
    adj.adj_btc = round(clamp(adj.adj_btc + contract_bias, -12.0, 12.0), 2)
    adj.adj_eth = round(clamp(adj.adj_eth + contract_bias * 0.9, -12.0, 12.0), 2)
    adj.adj_sol = round(clamp(adj.adj_sol + contract_bias * 0.7, -12.0, 12.0), 2)
    return adj
