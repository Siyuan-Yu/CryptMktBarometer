"""
公开资金面备用数据（无需 Key）
使用 CoinGecko 全球市场概览作 ETF/CoinGlass 未配置时的参考。
"""

from __future__ import annotations

import logging

from collectors.http_client import fetch_json

logger = logging.getLogger(__name__)


def fetch_coingecko_global(*, timeout: int = 15) -> tuple[str | None, str | None]:
    try:
        data = fetch_json(
            "https://api.coingecko.com/api/v3/global",
            timeout=timeout,
        )
        g = data.get("data") or {}
        cap_change = g.get("market_cap_change_percentage_24h_usd")
        vol = g.get("total_volume", {}).get("usd")
        parts = []
        if cap_change is not None:
            parts.append(f"全球市值24h {cap_change:+.2f}%")
        if vol:
            parts.append(f"24h成交额约 ${vol/1e9:.0f}B")
        if parts:
            return "CoinGecko：" + "，".join(parts) + "（公开备用）", None
        return None, "CoinGecko：无有效字段"
    except Exception as exc:
        return None, f"CoinGecko：{exc}"
