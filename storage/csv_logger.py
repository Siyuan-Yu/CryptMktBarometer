"""
CSV 简易日志
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from core.config_loader import PROJECT_ROOT, load_config

FETCH_LOG_FILENAME = "fetch_history.csv"
NEWS_LOG_FILENAME = "news_snapshot.csv"
SCORE_LOG_FILENAME = "score_history.csv"
WEIGHT_LOG_FILENAME = "weight_history.csv"
_WEIGHT_COLUMNS = [
    "update_time",
    "method",
    "macro",
    "regulation",
    "funding",
    "fundamentals",
    "next_recalc_at",
    "impact_samples",
]
_FETCH_COLUMNS = ["fetch_time", "duration_sec", "success", "error_count", "summary"]
_SCORE_COLUMNS = [
    "fetch_time",
    "total_score",
    "rating",
    "macro",
    "regulation",
    "funding",
    "fundamentals",
]
_NEWS_COLUMNS = [
    "fetch_time",
    "rank",
    "title",
    "source",
    "url",
    "impact_score",
    "keywords",
]


def _log_dir() -> Path:
    cfg = load_config()
    rel = cfg.get("storage", {}).get("log_dir", "data/logs")
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_fetch_log_row(
    *,
    fetch_time: datetime,
    duration_sec: float,
    success: bool,
    error_count: int,
    summary: str,
) -> Path:
    log_dir = _log_dir()
    file_path = log_dir / FETCH_LOG_FILENAME
    write_header = not file_path.exists()

    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_FETCH_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_sec": round(duration_sec, 2),
                "success": int(success),
                "error_count": error_count,
                "summary": summary,
            }
        )
    return file_path


def append_news_snapshot(
    fetch_time: datetime,
    top_news: list[dict],
) -> Path | None:
    """每轮 TOP10 资讯写入快照 CSV（无资讯时跳过）。"""
    if not top_news:
        return None

    file_path = _log_dir() / NEWS_LOG_FILENAME
    write_header = not file_path.exists()
    ts = fetch_time.strftime("%Y-%m-%d %H:%M:%S")

    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_NEWS_COLUMNS)
        if write_header:
            writer.writeheader()
        for i, row in enumerate(top_news, start=1):
            writer.writerow(
                {
                    "fetch_time": ts,
                    "rank": i,
                    "title": (row.get("title") or "")[:200],
                    "source": row.get("source", ""),
                    "url": row.get("url", ""),
                    "impact_score": row.get("impact_score", 0),
                    "keywords": " | ".join(row.get("keywords") or []),
                }
            )
    return file_path


def append_score_history(
    fetch_time: datetime,
    *,
    total_score: float,
    rating: str,
    categories: list[dict],
) -> Path:
    """每轮分项得分与综合总分写入历史 CSV。"""
    file_path = _log_dir() / SCORE_LOG_FILENAME
    write_header = not file_path.exists()

    def _pts(name: str) -> str:
        for c in categories:
            if c.get("name") == name:
                s = c.get("score")
                return "" if s is None else str(s)
        return ""

    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_SCORE_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_score": round(total_score, 1),
                "rating": rating,
                "macro": _pts("宏观数据"),
                "regulation": _pts("全球监管政策"),
                "funding": _pts("资金链上数据"),
                "fundamentals": _pts("ETH/SOL 币种基本面"),
            }
        )
    return file_path


def append_weight_history(
    *,
    weights: dict[str, int],
    method: str,
    next_recalc_at: str,
    impact_samples: int = 0,
) -> Path:
    """每次动态权重更新写入日志（永久追加，不覆盖）。"""
    file_path = _log_dir() / WEIGHT_LOG_FILENAME
    write_header = not file_path.exists()
    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_WEIGHT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "method": method,
                "macro": weights.get("macro", ""),
                "regulation": weights.get("regulation", ""),
                "funding": weights.get("funding", ""),
                "fundamentals": weights.get("fundamentals", ""),
                "next_recalc_at": next_recalc_at,
                "impact_samples": impact_samples,
            }
        )
    return file_path
