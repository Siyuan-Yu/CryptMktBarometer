"""
免费公开链上 / 宏观 API 拉取（无舆情、纯数值）。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.http_client import fetch_json

logger = logging.getLogger(__name__)


def fetch_fear_greed(*, timeout: int = 15) -> tuple[int | None, str, str | None]:
    """Alternative.me 恐惧贪婪指数 0~100。"""
    try:
        data = fetch_json("https://api.alternative.me/fng/", params={"limit": 1}, timeout=timeout)
        row = (data.get("data") or [{}])[0]
        val = int(row.get("value", 0))
        label = str(row.get("value_classification") or "")
        return val, label, None
    except Exception as exc:
        logger.warning("恐惧贪婪指数拉取失败: %s", exc)
        return None, "", str(exc)


def fetch_btc_hashrate_latest(*, timeout: int = 20) -> tuple[float | None, str | None]:
    """Blockchain.info 哈希率最新值（矿工活跃度代理）。"""
    try:
        data = fetch_json(
            "https://api.blockchain.info/charts/hash-rate",
            params={"timespan": "5days", "format": "json", "rollingAverage": "8hours"},
            timeout=timeout,
        )
        values = data.get("values") or []
        if len(values) < 2:
            return None, "哈希率数据不足"
        prev_y = float(values[-2].get("y") or 0)
        last_y = float(values[-1].get("y") or 0)
        if prev_y <= 0:
            return 0.0, None
        chg_pct = (last_y - prev_y) / prev_y * 100.0
        return round(chg_pct, 3), None
    except Exception as exc:
        logger.warning("BTC 哈希率拉取失败: %s", exc)
        return None, str(exc)


def fetch_eth_onchain_stats(*, timeout: int = 15) -> tuple[float | None, float | None, str | None]:
    """Blockchair ETH：24h 成交量与最大单笔（质押/大额异动代理）。"""
    try:
        data = fetch_json("https://api.blockchair.com/ethereum/stats", timeout=timeout)
        stats = data.get("data") or {}
        vol = float(stats.get("volume_24h_approximate") or 0)
        largest = 0.0
        lt = stats.get("largest_transaction_24h") or {}
        if isinstance(lt, dict):
            largest = float(lt.get("value_usd") or lt.get("value") or 0)
        return vol, largest, None
    except Exception as exc:
        logger.warning("ETH 链上统计拉取失败: %s", exc)
        return None, None, str(exc)


def fetch_sol_tvl_chg_pct(*, timeout: int = 20) -> tuple[float | None, str | None]:
    """DeFiLlama Solana TVL 近两次快照涨跌幅 %。"""
    try:
        rows = fetch_json("https://api.llama.fi/v2/historicalChainTvl/Solana", timeout=timeout)
        if not isinstance(rows, list) or len(rows) < 2:
            return None, "SOL TVL 历史不足"
        prev = float(rows[-2].get("tvl") or 0)
        last = float(rows[-1].get("tvl") or 0)
        if prev <= 0:
            return 0.0, None
        return round((last - prev) / prev * 100.0, 3), None
    except Exception as exc:
        logger.warning("SOL TVL 拉取失败: %s", exc)
        return None, str(exc)


def fetch_global_market_coingecko(*, timeout: int = 15) -> tuple[float | None, float | None, str | None]:
    """CoinGecko 全球市值/成交额 24h 变化 %（CMC 免费替代）。"""
    try:
        data = fetch_json("https://api.coingecko.com/api/v3/global", timeout=timeout)
        d = data.get("data") or {}
        mcap_chg = float(d.get("market_cap_change_percentage_24h_usd") or 0)
        vol = d.get("total_volume") or {}
        vol_usd = float(vol.get("usd") or 0) if isinstance(vol, dict) else 0.0
        return round(mcap_chg, 3), vol_usd, None
    except Exception as exc:
        logger.warning("CoinGecko 全球指标拉取失败: %s", exc)
        return None, None, str(exc)


def fetch_global_market_cmc(api_key: str, *, timeout: int = 15) -> tuple[float | None, float | None, str | None]:
    """CoinMarketCap 全球指标（需 API Key）。"""
    if not api_key or not str(api_key).strip():
        return None, None, "未配置 coinmarketcap API Key"
    try:
        import requests

        resp = requests.get(
            "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest",
            headers={
                "X-CMC_PRO_API_KEY": api_key.strip(),
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        q = (data.get("data") or {}).get("quote", {}).get("USD", {})
        pct = float(q.get("total_market_cap_change_24h_percent") or 0)
        vol = float(q.get("total_volume_24h") or 0)
        return round(pct, 3), vol, None
    except Exception as exc:
        logger.warning("CMC 全球指标拉取失败: %s", exc)
        return None, None, str(exc)


def fetch_glassnode_metric(
    api_key: str,
    metric_path: str,
    *,
    asset: str = "BTC",
    timeout: int = 15,
) -> tuple[float | None, str | None]:
    """Glassnode 免费档单指标（需 API Key）。"""
    if not api_key or not str(api_key).strip():
        return None, "未配置 glassnode API Key"
    try:
        data = fetch_json(
            f"https://api.glassnode.com/v1/metrics/{metric_path}",
            params={"a": asset, "api_key": api_key.strip(), "i": "24h"},
            timeout=timeout,
        )
        if isinstance(data, list) and data:
            return float(data[-1].get("v") or 0), None
        return None, "Glassnode 返回为空"
    except Exception as exc:
        return None, str(exc)
