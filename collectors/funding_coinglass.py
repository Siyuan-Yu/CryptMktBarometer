"""
CoinGlass 资金数据（ETF 流向、爆仓、持仓）
需 config.api_keys.coinglass，文档：https://docs.coinglass.com/
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from collectors.http_client import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

# CoinGlass Open API v4
CG_BASE = "https://open-api-v4.coinglass.com/api"


def _cg_get(api_key: str, path: str, *, timeout: int = 15) -> dict:
    url = f"{CG_BASE}{path}"
    headers = {**DEFAULT_HEADERS, "accept": "application/json", "CG-API-KEY": api_key.strip()}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if str(body.get("code")) not in ("0", "200", "success"):
        msg = body.get("msg") or body.get("message") or str(body)
        raise RuntimeError(msg)
    return body.get("data") or body


def fetch_etf_flow_summary(api_key: str, *, timeout: int = 15) -> tuple[str | None, str | None]:
    """比特币 ETF 资金流摘要（接口以 CoinGlass 文档为准，失败时返回错误）。"""
    try:
        data = _cg_get(api_key, "/etf/bitcoin/flow-history", timeout=timeout)
        if isinstance(data, list) and data:
            last = data[-1] if isinstance(data[-1], dict) else {}
            flow = last.get("flow") or last.get("netFlow") or last.get("net_flow")
            if flow is not None:
                return f"BTC ETF 最新净流入 {flow}（CoinGlass）", None
        return "BTC ETF：已连接，暂无结构化净流入字段", None
    except Exception as exc:
        return None, f"CoinGlass ETF：{exc}"


def fetch_liquidation_summary(api_key: str, *, timeout: int = 15) -> tuple[str | None, str | None]:
    try:
        data = _cg_get(api_key, "/futures/liquidation/aggregated-history", timeout=timeout)
        if isinstance(data, list) and data:
            last = data[-1]
            if isinstance(last, dict):
                total = last.get("total") or last.get("liquidation") or last.get("volUsd")
                if total is not None:
                    return f"全网爆仓(最近) {total} USD", None
        return "爆仓数据：已连接", None
    except Exception as exc:
        return None, f"CoinGlass 爆仓：{exc}"


def fetch_oi_summary(api_key: str, *, timeout: int = 15) -> tuple[str | None, str | None]:
    try:
        data = _cg_get(api_key, "/futures/openInterest/aggregated-history", timeout=timeout)
        if isinstance(data, list) and len(data) >= 2:
            a, b = data[-2], data[-1]
            if isinstance(a, dict) and isinstance(b, dict):
                oi_a = a.get("openInterest") or a.get("oi")
                oi_b = b.get("openInterest") or b.get("oi")
                if oi_a and oi_b:
                    try:
                        chg = (float(oi_b) - float(oi_a)) / float(oi_a) * 100
                        return f"合约持仓较前段 {chg:+.2f}%", None
                    except (TypeError, ValueError):
                        pass
        return "持仓数据：已连接", None
    except Exception as exc:
        return None, f"CoinGlass 持仓：{exc}"
