"""
历史资讯归档 — 追加写入 news_snapshot.csv，不覆盖已有数据
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from core.config_loader import PROJECT_ROOT, load_config

_COLUMNS = ["fetch_time", "rank", "title", "source", "url", "impact_score", "keywords"]


def _csv_path() -> Path:
    cfg = load_config()
    rel = cfg.get("storage", {}).get("log_dir", "data/logs")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p / "news_snapshot.csv"


def _existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            keys.add(f"{row.get('title','')}|{row.get('url','')}")
    return keys


def append_news_rows(rows: list[dict], *, fetch_time: str | None = None) -> int:
    """
    追加资讯到 news_snapshot.csv（跳过已存在 title+url）。
    rows 字段：title, source, url, impact_score, keywords, published_at(optional)
    """
    path = _csv_path()
    existing = _existing_keys(path)
    ts = fetch_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_header = not path.exists()
    added = 0

    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        if write_header:
            w.writeheader()
        rank = 0
        for row in rows:
            key = f"{row.get('title','')}|{row.get('url','')}"
            if not row.get("title") or key in existing:
                continue
            rank += 1
            kw = row.get("keywords") or []
            if isinstance(kw, list):
                kw_str = " | ".join(kw[:3])
            else:
                kw_str = str(kw)
            pub = row.get("published_at") or ts
            if isinstance(pub, datetime):
                pub = pub.strftime("%Y-%m-%d %H:%M:%S")
            w.writerow(
                {
                    "fetch_time": pub if row.get("use_published_as_fetch") else ts,
                    "rank": rank,
                    "title": (row.get("title") or "")[:300],
                    "source": row.get("source", ""),
                    "url": row.get("url", ""),
                    "impact_score": row.get("impact_score", 0),
                    "keywords": kw_str,
                }
            )
            existing.add(key)
            added += 1
    return added
