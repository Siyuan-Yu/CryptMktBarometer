"""
CFGI.io 开发者 API 客户端（需 config api_keys.cfgi）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from collectors.http_client import fetch_json
from core.config_loader import load_config

logger = logging.getLogger(__name__)

_TOKEN_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}


def _cfgi_settings(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    ds = cfg.get("data_sources", {}).get("cfgi", {})
    keys = cfg.get("api_keys", {})
    return {
        "enabled": bool(ds.get("enabled", True)),
        "api_key": (keys.get("cfgi") or "").strip(),
        "base_url": (ds.get("base_url") or "https://cfgi.io/api").rstrip("/"),
        "period": ds.get("period", "1d"),
        "latest_path": ds.get("latest_path", "/feargreed/{token}/{period}"),
        "history_path": ds.get(
            "history_path", "/feargreed/{token}/{period}/history"
        ),
        "timeout": int(cfg.get("collector", {}).get("request_timeout_sec", 15)),
    }


def _token_for_symbol(symbol: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    custom = (cfg.get("data_sources", {}).get("cfgi", {}).get("tokens") or {})
    sym = symbol.upper()
    return custom.get(sym, _TOKEN_MAP.get(sym, sym.lower()))


def _extract_value(row: dict) -> int | None:
    for key in ("value", "score", "cfgi", "fear_greed", "fearGreed"):
        if key in row and row[key] is not None:
            try:
                return int(float(row[key]))
            except (TypeError, ValueError):
                pass
    return None


def _extract_date(row: dict) -> str | None:
    for key in ("date", "trade_date", "day", "timestamp", "time"):
        if key not in row or row[key] is None:
            continue
        raw = str(row[key])
        if len(raw) >= 10 and raw[4] == "-":
            return raw[:10]
        try:
            if raw.isdigit() and len(raw) >= 10:
                ts = int(raw[:10])
                return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    return None


def _parse_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "results", "history", "items", "rows"):
        block = payload.get(key)
        if isinstance(block, list):
            return [r for r in block if isinstance(r, dict)]
        if isinstance(block, dict):
            nested = block.get("data") or block.get("history")
            if isinstance(nested, list):
                return [r for r in nested if isinstance(r, dict)]
    if _extract_value(payload) is not None:
        return [payload]
    return []


def fetch_cfgi_latest(symbol: str, *, cfg: dict | None = None) -> tuple[int | None, str | None]:
    """拉取单币种最新 CFGI 分。"""
    settings = _cfgi_settings(cfg)
    if not settings["enabled"] or not settings["api_key"]:
        return None, "cfgi api key missing"
    token = _token_for_symbol(symbol, cfg)
    period = settings["period"]
    path = settings["latest_path"].format(token=token, period=period)
    url = f"{settings['base_url']}{path}"
    try:
        data = fetch_json(
            url,
            params={"api_key": settings["api_key"], "apikey": settings["api_key"]},
            timeout=settings["timeout"],
        )
        rows = _parse_rows(data)
        if not rows:
            return None, "cfgi empty response"
        val = _extract_value(rows[-1])
        return val, None if val is not None else "cfgi parse failed"
    except Exception as exc:
        logger.warning("CFGI latest %s failed: %s", symbol, exc)
        return None, str(exc)


def fetch_cfgi_history(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    cfg: dict | None = None,
) -> tuple[list[dict], str | None]:
    """历史日频 CFGI：返回 [{trade_date, value}, ...]。"""
    settings = _cfgi_settings(cfg)
    if not settings["enabled"] or not settings["api_key"]:
        return [], "cfgi api key missing"
    token = _token_for_symbol(symbol, cfg)
    period = settings["period"]
    path = settings["history_path"].format(token=token, period=period)
    url = f"{settings['base_url']}{path}"
    params = {
        "api_key": settings["api_key"],
        "apikey": settings["api_key"],
        "start": start_date,
        "end": end_date,
        "from": start_date,
        "to": end_date,
    }
    try:
        data = fetch_json(url, params=params, timeout=settings["timeout"])
        rows = _parse_rows(data)
        out: list[dict] = []
        for row in rows:
            val = _extract_value(row)
            day = _extract_date(row)
            if val is None or not day:
                continue
            out.append({"trade_date": day, "value": int(val)})
        out.sort(key=lambda r: r["trade_date"])
        return out, None if out else "cfgi history empty"
    except Exception as exc:
        logger.warning("CFGI history %s failed: %s", symbol, exc)
        return [], str(exc)
