"""
从 score_history_4h（优先）或 score_history.csv 读取历史分数，供前端折线图。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from scoring.multi_asset import (
    compute_us_score_from_row,
    score_from_history_row,
    signal_from_score,
)
from storage.csv_logger import read_score_history
from storage.score_history_db import read_4h_series

_ASSET_LABELS = {
    "btc": "BTC",
    "eth": "ETH",
    "sol": "SOL",
    "us": "美股大盘",
}


def _parse_fetch_time(ts: str) -> datetime | None:
    ts = (ts or "").strip()
    if not ts:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _bucket_4h(dt: datetime) -> datetime:
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def _bucket_csv_rows(rows: list[dict[str, str]]) -> list[tuple[str, dict[str, str]]]:
    """CSV 按 4h 分桶，每桶保留最后一条。"""
    buckets: dict[datetime, dict[str, str]] = {}
    order: list[datetime] = []
    for row in rows:
        dt = _parse_fetch_time(row.get("fetch_time") or "")
        if not dt:
            continue
        key = _bucket_4h(dt)
        if key not in buckets:
            order.append(key)
        buckets[key] = row
    order.sort()
    return [(k.strftime("%Y-%m-%d %H:%M:%S"), buckets[k]) for k in order]


def _btc_score_from_csv_row(row: dict[str, str]) -> float | None:
    """BTC：优先 total_score；若与分项严重脱节则用分项之和。"""
    total = score_from_history_row(row, "btc")
    if total is None:
        return None
    parts = []
    for k in ("macro", "regulation", "funding", "fundamentals"):
        v = row.get(k)
        if v not in (None, ""):
            try:
                parts.append(float(v))
            except ValueError:
                pass
    if len(parts) == 4:
        part_sum = round(sum(parts), 1)
        if total < 20 and part_sum >= 35:
            return part_sum
    return total


def _build_from_csv_bucketed(
    rows: list[dict[str, str]],
    *,
    after_time: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """CSV 回退：仅处理 4h 桶，且 ETH/SOL 用批量百分位（避免 API 超时）。"""
    from scoring.symbol_scores import compute_normalized_scores_chronological

    bucketed = _bucket_csv_rows(rows)
    if after_time:
        bucketed = [(t, r) for t, r in bucketed if t > after_time]
    if not bucketed:
        return {k: [] for k in ("btc", "eth", "sol", "us")}

    slots = [
        datetime.strptime(t, "%Y-%m-%d %H:%M:%S") for t, _ in bucketed
    ]
    norm_map = compute_normalized_scores_chronological(slots, persist=False)

    series: dict[str, list[dict[str, Any]]] = {
        k: [] for k in ("btc", "eth", "sol", "us")
    }
    for ts, row in bucketed:
        base = {"time": ts, "rating": row.get("rating") or ""}
        sym_scores = norm_map.get(ts, {})
        btc = _btc_score_from_csv_row(row)
        if btc is not None:
            series["btc"].append(
                {
                    **base,
                    "score": btc,
                    "signal": signal_from_score(btc),
                }
            )
        for asset, sym in (("eth", "ETH"), ("sol", "SOL")):
            sc = sym_scores.get(sym)
            if sc is not None:
                series[asset].append(
                    {
                        **base,
                        "score": sc,
                        "signal": signal_from_score(sc),
                    }
                )
        us = compute_us_score_from_row(row)
        if us is not None:
            series["us"].append(
                {
                    **base,
                    "score": us,
                    "signal": signal_from_score(us),
                }
            )
    return series


def _merge_series(
    base: dict[str, list[dict[str, Any]]],
    extra: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """按 time 合并，extra 覆盖同时间点。"""
    out: dict[str, list[dict[str, Any]]] = {k: list(v) for k, v in base.items()}
    for asset, points in extra.items():
        by_time = {p["time"]: p for p in out.get(asset, [])}
        for p in points:
            by_time[p["time"]] = p
        out[asset] = sorted(by_time.values(), key=lambda x: x["time"])
    return out


def build_score_history_payload(*, since: str = "2025-01-01") -> dict[str, Any]:
    """返回四品种历史序列，供 /api/score-history 使用。"""
    series = read_4h_series(since=since)
    db_count = max(len(series[k]) for k in series)

    if db_count > 0:
        from storage.score_history_db import latest_4h_time

        last_db = latest_4h_time() or ""
        csv_rows = read_score_history(since=since)
        if last_db and csv_rows:
            newer = [
                r
                for r in csv_rows
                if (r.get("fetch_time") or "") > last_db
            ]
            if newer:
                extra = _build_from_csv_bucketed(newer, after_time=last_db)
                series = _merge_series(series, extra)
    elif read_score_history(since=since):
        series = _build_from_csv_bucketed(read_score_history(since=since))

    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_times: list[str] = []
    for pts in series.values():
        all_times.extend(p["time"] for p in pts)
    if all_times:
        end = max(all_times)

    point_count = max(len(series[k]) for k in series)

    return {
        "since": since,
        "until": end,
        "point_count": point_count,
        "labels": _ASSET_LABELS,
        "series": series,
        "signal_rule": f">={int(55)}多/<={int(45)}空",
    }
