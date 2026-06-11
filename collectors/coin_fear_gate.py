"""
预留：Gate.io ETH 单币种独立恐慌 API。

接入步骤：
1. 在 config api_keys.gate 填入 Key
2. 设置 data_sources.gate_fear.enabled: true
3. 实现 fetch_gate_eth_fear_latest / fetch_gate_eth_fear_history
4. 在 GateEthFearProvider 中取消 TODO 注释
"""

from __future__ import annotations

from typing import Any

from collectors.coin_fear_providers import FearSample
from core.config_loader import load_config


def _gate_settings(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    ds = cfg.get("data_sources", {}).get("gate_fear", {})
    keys = cfg.get("api_keys", {})
    return {
        "enabled": bool(ds.get("enabled", False)),
        "api_key": (keys.get("gate") or "").strip(),
        "base_url": (ds.get("base_url") or "").rstrip("/"),
        "latest_path": ds.get("latest_path", ""),
        "history_path": ds.get("history_path", ""),
        "timeout": int(cfg.get("collector", {}).get("request_timeout_sec", 15)),
    }


def fetch_gate_eth_fear_latest(
    trade_date: str,
    *,
    cfg: dict | None = None,
) -> FearSample | None:
    """拉取 Gate ETH 当日恐慌分（待对接）。"""
    settings = _gate_settings(cfg)
    if not settings["enabled"] or not settings["base_url"]:
        return None
    # TODO: requests.get(settings["base_url"] + settings["latest_path"], ...)
    return None


def fetch_gate_eth_fear_history(
    *,
    start_date: str,
    end_date: str,
    cfg: dict | None = None,
) -> list[FearSample]:
    """拉取 Gate ETH 历史恐慌（待对接）。"""
    _ = (start_date, end_date, cfg)
    return []
