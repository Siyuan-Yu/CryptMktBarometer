"""
实时现货价格（BTC / ETH / SOL）
数据源：Binance 公开 API，失败时回退 CoinGecko。
内存缓存，供 Web 每 5 秒轮询。
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

from collectors.http_client import DEFAULT_HEADERS, fetch_json

logger = logging.getLogger(__name__)

_SYMBOLS = ("BTC", "ETH", "SOL")
_BINANCE_PAIRS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
_COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}

_cache_lock = Lock()
_cache: dict[str, Any] = {"data": None, "updated_at": 0.0, "source": ""}


def _empty_ticker() -> dict[str, Any]:
    return {
        sym: {
            "symbol": sym,
            "price": None,
            "change_24h_pct": None,
            "updated_at": None,
        }
        for sym in _SYMBOLS
    }


def _fetch_binance(timeout: int = 10) -> dict[str, Any] | None:
    import requests

    url = "https://api.binance.com/api/v3/ticker/24hr"
    out: dict[str, Any] = {}
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for sym, pair in _BINANCE_PAIRS.items():
        resp = requests.get(
            url,
            params={"symbol": pair},
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        row = resp.json()
        out[sym] = {
            "symbol": sym,
            "price": float(row.get("lastPrice", 0)),
            "change_24h_pct": float(row.get("priceChangePercent", 0)),
            "updated_at": ts,
        }
    return out if len(out) == 3 else None


def _fetch_coingecko(timeout: int = 10) -> dict[str, Any] | None:
    ids = ",".join(_COINGECKO_IDS.values())
    url = "https://api.coingecko.com/api/v3/simple/price"
    data = fetch_json(
        url,
        params={
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        },
        timeout=timeout,
    )
    out: dict[str, Any] = {}
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for sym, cg_id in _COINGECKO_IDS.items():
        block = data.get(cg_id) or {}
        if "usd" not in block:
            continue
        out[sym] = {
            "symbol": sym,
            "price": float(block["usd"]),
            "change_24h_pct": float(block.get("usd_24h_change") or 0),
            "updated_at": ts,
        }
    return out if out else None


def fetch_live_prices(*, timeout: int = 10) -> dict[str, Any]:
    """拉取最新价格（直接请求，不走缓存）。"""
    tickers = _empty_ticker()
    source = "none"
    try:
        binance = _fetch_binance(timeout=timeout)
        if binance:
            tickers.update(binance)
            source = "binance"
    except Exception as exc:
        logger.debug("Binance 价格失败: %s", exc)

    if source != "binance":
        try:
            cg = _fetch_coingecko(timeout=timeout)
            if cg:
                tickers.update(cg)
                source = "coingecko"
        except Exception as exc:
            logger.warning("CoinGecko 价格失败: %s", exc)

    return {
        "tickers": tickers,
        "source": source,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_cached_prices(
    *,
    cache_seconds: float = 4.0,
    timeout: int = 10,
) -> dict[str, Any]:
    """带短缓存的价格（默认 4 秒，配合前端 5 秒轮询）。"""
    now = time.time()
    with _cache_lock:
        if (
            _cache.get("data")
            and now - float(_cache.get("updated_at") or 0) < cache_seconds
        ):
            return _cache["data"]

    data = fetch_live_prices(timeout=timeout)
    with _cache_lock:
        _cache["data"] = data
        _cache["updated_at"] = now
        _cache["source"] = data.get("source", "")
    return data
