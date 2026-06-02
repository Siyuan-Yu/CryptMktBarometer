"""
资金数据采集汇总
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from collectors.funding_coinglass import (
    fetch_etf_flow_summary,
    fetch_liquidation_summary,
    fetch_oi_summary,
)
from collectors.funding_public import fetch_coingecko_global

logger = logging.getLogger(__name__)


@dataclass
class FundingSnapshot:
    summary_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def category_summary(self) -> str:
        if not self.summary_lines:
            return "资金数据：本轮未获取到有效指标"
        return " | ".join(self.summary_lines)


def collect_funding(cfg: dict[str, Any]) -> FundingSnapshot:
    ds = cfg.get("data_sources", {}).get("funding", {})
    api_key = (cfg.get("api_keys", {}).get("coinglass") or "").strip()
    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))

    snap = FundingSnapshot()
    used_coinglass = False

    if api_key:
        if ds.get("coinglass_etf", False):
            text, err = fetch_etf_flow_summary(api_key, timeout=timeout)
            if text:
                snap.summary_lines.append(text)
                used_coinglass = True
            if err:
                snap.errors.append(err)
        if ds.get("coinglass_liquidation", False):
            text, err = fetch_liquidation_summary(api_key, timeout=timeout)
            if text:
                snap.summary_lines.append(text)
                used_coinglass = True
            if err:
                snap.errors.append(err)
        if ds.get("coinglass_oi", False):
            text, err = fetch_oi_summary(api_key, timeout=timeout)
            if text:
                snap.summary_lines.append(text)
                used_coinglass = True
            if err:
                snap.errors.append(err)
    else:
        if any(ds.get(k) for k in ("coinglass_etf", "coinglass_liquidation", "coinglass_oi")):
            snap.summary_lines.append("CoinGlass：未配置 api_keys.coinglass，已跳过")

    if not used_coinglass and any(ds.values()):
        text, err = fetch_coingecko_global(timeout=timeout)
        if text:
            snap.summary_lines.append(text)
        elif err:
            snap.errors.append(err)

    return snap
