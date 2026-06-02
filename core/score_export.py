"""
独立导出：四品种晴雨表分数历史（4 小时粒度 CSV）
仅读取 score_history.csv，不改动计分/存储逻辑。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from core.score_history import _score_from_row
from storage.csv_logger import read_score_history

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


def score_status(score: float) -> str:
    """多空状态：看多 / 看空 / 中性（与晴雨表 55/45 阈值一致）。"""
    if score >= 55:
        return "看多"
    if score < 45:
        return "看空"
    return "中性"


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


def build_score_history_export_rows(*, since: str = "2026-01-01") -> list[dict[str, Any]]:
    """生成导出行：time, symbol, score, status。"""
    raw = read_score_history(since=since)
    out: list[dict[str, Any]] = []

    for bucket_dt, row in _bucket_rows_4h(raw):
        time_label = _format_bucket(bucket_dt)
        for asset_key, symbol in _EXPORT_SYMBOLS:
            score = _score_from_row(row, asset_key)
            if score is None:
                continue
            out.append(
                {
                    "time": time_label,
                    "symbol": symbol,
                    "score": score,
                    "status": score_status(score),
                }
            )

    return out


def build_score_history_csv(*, since: str = "2026-01-01") -> str:
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
