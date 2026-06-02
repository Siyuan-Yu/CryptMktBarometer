"""
从 score_history.csv 读取历史分项分，并按品种视角合成历史总分（供前端折线图）。
不修改计分引擎，仅读取已有 CSV 并做展示层换算。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from storage.csv_logger import read_score_history

_CAT_ORDER = (
    "宏观数据",
    "全球监管政策",
    "资金链上数据",
    "ETH/SOL 币种基本面",
)

_BASE_WEIGHTS: dict[str, int] = {
    "宏观数据": 30,
    "全球监管政策": 30,
    "资金链上数据": 35,
    "ETH/SOL 币种基本面": 5,
}

_ASSET_NUDGES: dict[str, dict[str, int]] = {
    "btc": {},
    "eth": {"ETH/SOL 币种基本面": 6, "资金链上数据": -4},
    "sol": {"ETH/SOL 币种基本面": 8, "宏观数据": -4},
    "us": {
        "宏观数据": 12,
        "全球监管政策": 3,
        "资金链上数据": -8,
        "ETH/SOL 币种基本面": -7,
    },
}

_ASSET_LABELS = {
    "btc": "BTC",
    "eth": "ETH",
    "sol": "SOL",
    "us": "美股大盘",
}


def _parse_float(val: str | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _weights_for_asset(asset: str) -> dict[str, int]:
    w = dict(_BASE_WEIGHTS)
    for name, delta in _ASSET_NUDGES.get(asset, {}).items():
        w[name] = max(1, w.get(name, 0) + delta)
    total = sum(w.values()) or 1
    return {k: round(v * 100 / total) for k, v in w.items()}


def _score_from_row(row: dict[str, str], asset: str) -> float | None:
    if asset == "btc":
        return _parse_float(row.get("total_score"))

    scores = {
        "宏观数据": _parse_float(row.get("macro")),
        "全球监管政策": _parse_float(row.get("regulation")),
        "资金链上数据": _parse_float(row.get("funding")),
        "ETH/SOL 币种基本面": _parse_float(row.get("fundamentals")),
    }
    weights = _weights_for_asset(asset)
    total_w = 0.0
    acc = 0.0
    for name in _CAT_ORDER:
        s = scores.get(name)
        if s is None:
            continue
        wt = weights.get(name, 0)
        acc += s * wt
        total_w += wt
    if total_w <= 0:
        return _parse_float(row.get("total_score"))
    return round(acc / total_w, 1)


def build_score_history_payload(*, since: str = "2026-01-01") -> dict[str, Any]:
    """返回四品种历史序列，供 /api/score-history 使用。"""
    rows = read_score_history(since=since)
    series: dict[str, list[dict[str, Any]]] = {
        k: [] for k in ("btc", "eth", "sol", "us")
    }

    for row in rows:
        ts = row.get("fetch_time") or ""
        if not ts:
            continue
        point_base = {
            "time": ts,
            "rating": row.get("rating") or "",
        }
        for asset in series:
            score = _score_from_row(row, asset)
            if score is None:
                continue
            series[asset].append({**point_base, "score": score})

    start = since
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if rows:
        end = rows[-1].get("fetch_time") or end

    return {
        "since": start,
        "until": end,
        "point_count": len(rows),
        "labels": _ASSET_LABELS,
        "series": series,
    }
