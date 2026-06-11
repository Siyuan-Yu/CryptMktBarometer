"""
链上客观因子 → 固定权重加减分（无主观舆情）。
"""

from __future__ import annotations

from storage.onchain_db import OnchainSnapshot
from scoring.utils import clamp

# 恐惧贪婪：全市场 ±3~6
_FNG_SCALE = 6.0
_FNG_MIN = 3.0

# 品种链上固定加减上限
_BTC_CHAIN_CAP = 5.0
_ETH_CHAIN_CAP = 10.0
_SOL_CHAIN_CAP = 10.0
_MARKET_CAP = 5.0

# 大额进场时 ETH/SOL 基准分抬升下限
_ETH_FLOOR = 42.0
_SOL_FLOOR = 40.0


def fear_greed_adjustment(value: int | None) -> float:
    """
    极端恐惧 → 偏多 +3~6；极端贪婪 → 偏空 -3~-6。
    逆向情绪映射：(50 - value) / 50 * 6
    """
    if value is None:
        return 0.0
    raw = (50.0 - float(value)) / 50.0 * _FNG_SCALE
    if abs(raw) < _FNG_MIN and raw != 0:
        raw = _FNG_MIN if raw > 0 else -_FNG_MIN
    return round(clamp(raw, -_FNG_SCALE, _FNG_SCALE), 2)


def btc_miner_adjustment(hashrate_chg_pct: float | None) -> float:
    if hashrate_chg_pct is None:
        return 0.0
    chg = hashrate_chg_pct
    if chg >= 3.0:
        return 5.0
    if chg >= 1.0:
        return 3.0
    if chg <= -3.0:
        return -5.0
    if chg <= -1.0:
        return -3.0
    return round(chg * 1.2, 2)


def eth_flow_adjustment(
    volume_24h: float | None,
    largest_tx: float | None,
    prev_volume: float | None = None,
) -> float:
    adj = 0.0
    if largest_tx is not None:
        if largest_tx >= 50_000_000:
            adj += 8.0
        elif largest_tx >= 10_000_000:
            adj += 5.0
        elif largest_tx >= 1_000_000:
            adj += 2.0
    if volume_24h is not None and prev_volume and prev_volume > 0:
        vol_chg = (volume_24h - prev_volume) / prev_volume * 100.0
        if vol_chg >= 15:
            adj += 4.0
        elif vol_chg >= 5:
            adj += 2.0
        elif vol_chg <= -15:
            adj -= 3.0
    elif volume_24h is not None and volume_24h >= 5e9:
        adj += 2.0
    return round(clamp(adj, -_ETH_CHAIN_CAP, _ETH_CHAIN_CAP), 2)


def sol_flow_adjustment(tvl_chg_pct: float | None) -> float:
    if tvl_chg_pct is None:
        return 0.0
    chg = tvl_chg_pct
    if chg >= 5.0:
        return 8.0
    if chg >= 2.0:
        return 5.0
    if chg >= 0.5:
        return 2.0
    if chg <= -5.0:
        return -6.0
    if chg <= -2.0:
        return -3.0
    return round(chg * 1.5, 2)


def market_global_adjustment(
    mcap_chg_pct: float | None,
    volume_chg_proxy: float | None = None,
) -> float:
    adj = 0.0
    if mcap_chg_pct is not None:
        if mcap_chg_pct >= 3.0:
            adj += 4.0
        elif mcap_chg_pct >= 1.0:
            adj += 2.0
        elif mcap_chg_pct <= -3.0:
            adj -= 4.0
        elif mcap_chg_pct <= -1.0:
            adj -= 2.0
    if volume_chg_proxy is not None:
        adj += clamp(volume_chg_proxy * 0.5, -2.0, 2.0)
    return round(clamp(adj, -_MARKET_CAP, _MARKET_CAP), 2)


def etf_flow_proxy_adjustment(mcap_chg_pct: float | None) -> float:
    """现货 ETF 资金流代理：用全市场市值 24h 变化近似 ±3~5。"""
    if mcap_chg_pct is None:
        return 0.0
    if mcap_chg_pct >= 4.0:
        return 5.0
    if mcap_chg_pct >= 1.5:
        return 3.0
    if mcap_chg_pct <= -4.0:
        return -5.0
    if mcap_chg_pct <= -1.5:
        return -3.0
    return round(mcap_chg_pct * 0.8, 2)


def compute_adjustments(
    snap: OnchainSnapshot,
    *,
    prev: OnchainSnapshot | None = None,
) -> OnchainSnapshot:
    """根据快照计算各品种客观加减分，写回 snap.adj_*。"""
    # 大盘恐慌改在最终分 apply_fear_adjustments 离散加减，链上层不再叠加 F&G
    fng = 0.0
    market = market_global_adjustment(snap.market_cap_chg_24h_pct)
    etf = etf_flow_proxy_adjustment(snap.market_cap_chg_24h_pct)
    btc_m = btc_miner_adjustment(snap.btc_hashrate_chg_pct)
    eth_f = eth_flow_adjustment(
        snap.eth_volume_24h_usd,
        snap.eth_largest_tx_24h_usd,
        prev.eth_volume_24h_usd if prev else None,
    )
    sol_f = sol_flow_adjustment(snap.sol_tvl_chg_pct)

    snap.adj_market = round(clamp(fng + market + etf, -_MARKET_CAP, _MARKET_CAP), 2)
    snap.adj_btc = round(clamp(fng + market + etf + btc_m, -12.0, 12.0), 2)
    snap.adj_eth = round(clamp(fng + market + etf + eth_f, -12.0, 12.0), 2)
    snap.adj_sol = round(clamp(fng + market + etf + sol_f, -12.0, 12.0), 2)

    parts = [
        f"恐惧贪婪{snap.fear_greed}({snap.fear_greed_class})→计分层离散处理",
        f"BTC矿工哈希率{snap.btc_hashrate_chg_pct or 0:+.2f}%→{btc_m:+.1f}",
        f"ETH链上量/大单→{eth_f:+.1f}",
        f"SOL TVL{snap.sol_tvl_chg_pct or 0:+.2f}%→{sol_f:+.1f}",
        f"全球市值24h{snap.market_cap_chg_24h_pct or 0:+.2f}%→市场{market:+.1f}/ETF代理{etf:+.1f}",
    ]
    snap.summary = "；".join(parts)
    return snap


def apply_symbol_adjustments(
    scores: dict[str, float],
    snap: OnchainSnapshot | None,
) -> dict[str, float]:
    """将客观链上调整叠加到品种分，并执行 ETH/SOL 大额进场基准抬升。"""
    if not snap:
        return scores
    out = dict(scores)
    mapping = {
        "BTC": snap.adj_btc,
        "ETH": snap.adj_eth,
        "SOL": snap.adj_sol,
    }
    for sym, adj in mapping.items():
        if sym not in out:
            continue
        total = round(clamp(out[sym] + adj, 0.0, 100.0), 1)
        if sym == "ETH" and snap.adj_eth >= 4.0:
            total = max(total, _ETH_FLOOR)
        if sym == "SOL" and snap.adj_sol >= 4.0:
            total = max(total, _SOL_FLOOR)
        out[sym] = total
    return out
