"""
独立导出：四品种晴雨表分数历史（4 小时粒度 CSV）
仅读取 score_history.csv，不改动计分/存储逻辑。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from scoring.multi_asset import score_status_label
from storage.score_history_db import read_4h_series
from core.score_history import _build_from_csv_bucketed
from storage.csv_logger import read_score_history
from storage.score_history_db import latest_4h_time

_EXPORT_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("btc", "BTC"),
    ("eth", "ETH"),
    ("sol", "SOL"),
    ("us", "美股"),
)

_EXPORT_COLUMNS = ("time", "symbol", "score", "status")
_EXPORT_FILENAME = "score_history_4h.csv"


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
    """对齐到 4 小时窗口起点（0/4/8/12/16/20 点）。"""
    hour = (dt.hour // 4) * 4
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def _format_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _bucket_rows_4h(rows: list[dict[str, str]]) -> list[tuple[datetime, dict[str, str]]]:
    """按 4 小时分桶，每桶保留最后一条原始记录。"""
    buckets: dict[datetime, dict[str, str]] = {}
    order: list[datetime] = []

    for row in rows:
        ts = row.get("fetch_time") or ""
        dt = _parse_fetch_time(ts)
        if not dt:
            continue
        key = _bucket_4h(dt)
        if key not in buckets:
            order.append(key)
        buckets[key] = row

    order.sort()
    return [(k, buckets[k]) for k in order]


def build_score_history_export_rows(*, since: str = "2025-01-01") -> list[dict[str, Any]]:
    """生成导出行：time, symbol, score, status。"""
    series = read_4h_series(since=since)
    last_db = latest_4h_time() or ""
    csv_rows = read_score_history(since=since)
    if last_db and csv_rows:
        newer = [r for r in csv_rows if (r.get("fetch_time") or "") > last_db]
        if newer:
            from core.score_history import _merge_series

            series = _merge_series(series, _build_from_csv_bucketed(newer))
    elif not max(len(series[k]) for k in series) and csv_rows:
        series = _build_from_csv_bucketed(csv_rows)

    out: list[dict[str, Any]] = []
    sym_map = {"btc": "BTC", "eth": "ETH", "sol": "SOL", "us": "美股"}
    for asset_key, symbol in _EXPORT_SYMBOLS:
        label = sym_map.get(asset_key, symbol)
        for p in series.get(asset_key, []):
            t = p.get("time") or ""
            dt = _parse_fetch_time(t)
            time_label = _format_bucket(dt) if dt else t[:16]
            score = p.get("score")
            if score is None:
                continue
            out.append(
                {
                    "time": time_label,
                    "symbol": label,
                    "score": score,
                    "status": score_status_label(float(score)),
                }
            )
    out.sort(key=lambda r: (r["time"], r["symbol"]))
    return out


def build_score_history_csv(*, since: str = "2025-01-01") -> str:
    """返回 UTF-8 BOM CSV 文本，便于 Excel 打开中文。"""
    rows = build_score_history_export_rows(since=since)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "time": row["time"],
                "symbol": row["symbol"],
                "score": row["score"],
                "status": row["status"],
            }
        )
    return "\ufeff" + buf.getvalue()
