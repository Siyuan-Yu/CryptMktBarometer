"""
FRED 宏观数据（美债10Y、联邦基金利率、经济发布日历）
需 config.api_keys.fred，免费申请：https://fred.stlouisfed.org/docs/api/api_key.html
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from collectors.http_client import fetch_json

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"


def _fred_get(
    api_key: str,
    endpoint: str,
    *,
    timeout: int = 15,
    **params: Any,
) -> dict:
    params["api_key"] = api_key.strip()
    params["file_type"] = "json"
    url = f"{FRED_BASE}/{endpoint}"
    return fetch_json(url, params=params, timeout=timeout)


def fetch_series_latest(
    api_key: str,
    series_id: str,
    *,
    limit: int = 2,
    timeout: int = 15,
) -> tuple[float | None, float | None, str | None]:
    """
    取最近 1～2 个有效观测值。
    :return: (最新值, 前一日值或 None, 错误信息)
    """
    try:
        data = _fred_get(
            api_key,
            "series/observations",
            timeout=timeout,
            series_id=series_id,
            sort_order="desc",
            limit=limit,
        )
    except Exception as exc:
        return None, None, f"FRED {series_id}：{exc}"

    obs = [
        o
        for o in (data.get("observations") or [])
        if o.get("value") not in (".", None, "")
    ]
    if not obs:
        return None, None, f"FRED {series_id}：无有效数据"

    latest = float(obs[0]["value"])
    prev = float(obs[1]["value"]) if len(obs) > 1 else None
    return latest, prev, None


def fetch_upcoming_releases(
    api_key: str,
    *,
    days_ahead: int = 14,
    limit: int = 8,
    timeout: int = 15,
) -> tuple[list[str], str | None]:
    """近期重要经济数据发布（FRED releases dates）。"""
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    try:
        data = _fred_get(
            api_key,
            "releases/dates",
            timeout=timeout,
            realtime_start=today.isoformat(),
            realtime_end=end.isoformat(),
            include_release_dates_with_no_data="true",
            order_by="release_date",
            sort_order="asc",
            limit=limit,
        )
    except Exception as exc:
        return [], f"FRED 经济日历：{exc}"

    lines: list[str] = []
    for row in data.get("release_dates") or []:
        name = row.get("release_name") or "发布"
        date = row.get("date", "")
        lines.append(f"{date} {name}")
    return lines, None
