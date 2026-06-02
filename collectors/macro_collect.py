"""
宏观数据采集汇总
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from collectors.macro_fedwatch import fetch_policy_expectation_proxy
from collectors.macro_fred import fetch_series_latest, fetch_upcoming_releases
from collectors.macro_treasury import fetch_10y_from_treasury

logger = logging.getLogger(__name__)


@dataclass
class MacroSnapshot:
    summary_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    treasury_10y: float | None = None
    treasury_10y_chg_bps: float | None = None
    fed_expectation: str | None = None
    calendar_hints: list[str] = field(default_factory=list)

    @property
    def category_summary(self) -> str:
        if not self.summary_lines:
            return "宏观数据：本轮未获取到有效指标"
        return " | ".join(self.summary_lines)


def _bps_change(latest: float, prev: float | None) -> float | None:
    if prev is None:
        return None
    return round((latest - prev) * 100, 1)


def collect_macro(cfg: dict[str, Any]) -> MacroSnapshot:
    ds = cfg.get("data_sources", {}).get("macro", {})
    api_key = (cfg.get("api_keys", {}).get("fred") or "").strip()
    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))

    snap = MacroSnapshot()

    # --- 美债 10Y ---
    if ds.get("treasury_10y", False):
        latest, prev, err = None, None, None
        if api_key:
            latest, prev, err = fetch_series_latest(api_key, "DGS10", timeout=timeout)
            if not err:
                snap.summary_lines.append(f"10Y美债(FRED) {latest:.2f}%")
        if latest is None:
            latest, prev, err2 = fetch_10y_from_treasury(timeout=timeout)
            if latest is not None:
                snap.summary_lines.append(f"10Y美债(财政部) {latest:.2f}%")
                err = None
            elif err:
                snap.errors.append(err)
            if err2 and latest is None:
                snap.errors.append(err2)

        if latest is not None:
            snap.treasury_10y = latest
            snap.treasury_10y_chg_bps = _bps_change(latest, prev)
            if snap.treasury_10y_chg_bps is not None:
                snap.summary_lines.append(f"10Y较前日 {snap.treasury_10y_chg_bps:+.0f}bp")

    # --- CME FedWatch proxy ---
    if ds.get("cme_fedwatch", False):
        text, err = fetch_policy_expectation_proxy(api_key, timeout=timeout)
        if text:
            snap.fed_expectation = text
            snap.summary_lines.append(f"政策预期：{text[:80]}")
        elif err:
            if "请配置" in err:
                snap.summary_lines.append(err[:100])
            else:
                snap.errors.append(err)

    # --- FRED 经济日历 ---
    if ds.get("fred_calendar", False):
        if not api_key:
            snap.summary_lines.append("FRED经济日历：未配置 fred API Key")
        else:
            dates, err = fetch_upcoming_releases(api_key, timeout=timeout)
            if dates:
                snap.calendar_hints = dates
                snap.summary_lines.append(f"近期发布 {len(dates)} 条")
            if err:
                snap.errors.append(err)

    return snap
