#!/usr/bin/env python3
"""
独立补全脚本：生成 2026-01-01 至今、每 4 小时一条的晴雨表分项历史分数。

- 分项计分逻辑与 scoring/engine.compute_scores 一致（调用 macro_score / funding_score 等）
- 价格信号来自 market.db 小时 K 线（不足时自动 Binance 回填）
- 写入 data/logs/score_history.csv（前端 /api/score-history 直接读取，无需改 Flask）
- 同步写入 market.db 表 score_history_4h

用法（项目根目录）：
    python generate_history_4h.py
    python generate_history_4h.py --start 2026-01-01 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_loader import PROJECT_ROOT, load_config
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from scoring.multi_asset import (
    compute_btc_category_row,
    compute_symbol_scores_at,
    compute_us_score_from_row,
)
from storage import price_db
from storage.csv_logger import SCORE_LOG_FILENAME, _SCORE_COLUMNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_history_4h")

DEFAULT_START = "2025-01-01"
SYMBOLS = ["BTC", "ETH", "SOL"]
MIN_CANDLES = 500


def _log_dir() -> Path:
    cfg = load_config()
    rel = cfg.get("storage", {}).get("log_dir", "data/logs")
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_path() -> Path:
    cfg = load_config()
    rel = cfg.get("weight_optimizer", {}).get("price_db", "data/market.db")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _parse_ts(ts: str) -> datetime | None:
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
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def iter_4h_slots(start: datetime, end: datetime) -> list[datetime]:
    cur = _bucket_4h(start)
    end_b = _bucket_4h(end)
    slots: list[datetime] = []
    while cur <= end_b:
        slots.append(cur)
        cur += timedelta(hours=4)
    return slots


def compute_scores_at(at: datetime) -> dict[str, str | float]:
    """在指定时刻生成 CSV 行（四分项 + BTC 总分）。"""
    return compute_btc_category_row(at)


def row_to_csv_dict(row: dict) -> dict[str, str]:
    return {
        "fetch_time": str(row["fetch_time"]),
        "total_score": str(row["total_score"]),
        "rating": str(row["rating"]),
        "macro": str(row["macro"]),
        "regulation": str(row["regulation"]),
        "funding": str(row["funding"]),
        "fundamentals": str(row["fundamentals"]),
    }


def load_existing_buckets(since: str) -> dict[datetime, dict[str, str]]:
    path = _log_dir() / SCORE_LOG_FILENAME
    if not path.exists():
        return {}
    since_dt = f"{since} 00:00:00"
    buckets: dict[datetime, dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            ts = (raw.get("fetch_time") or "").strip()
            if not ts or ts < since_dt:
                continue
            dt = _parse_ts(ts)
            if not dt:
                continue
            key = _bucket_4h(dt)
            buckets[key] = {k: (raw.get(k) or "").strip() for k in _SCORE_COLUMNS}
    return buckets


def ensure_prices(start_date: str, end_date: str) -> None:
    price_db.init_schema()
    need = any(price_db.count_candles(s) < MIN_CANDLES for s in SYMBOLS)
    if not need:
        logger.info("market.db 小时 K 线已充足，跳过回填")
        return
    logger.info("正在从 Binance 回填 %s ~ %s 小时 K 线…", start_date, end_date)
    from collectors.price_hourly import backfill_history

    counts = backfill_history(SYMBOLS, start_date, end_date)
    for sym, n in counts.items():
        logger.info("  %s: %d 根", sym, n)


def init_db_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS score_history_4h (
            fetch_time TEXT PRIMARY KEY,
            total_score REAL NOT NULL,
            rating TEXT,
            macro REAL,
            regulation REAL,
            funding REAL,
            fundamentals REAL,
            btc_score REAL,
            eth_score REAL,
            sol_score REAL,
            us_score REAL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_score_hist_4h_time ON score_history_4h(fetch_time)"
    )


def write_market_db(rows: list[dict]) -> int:
    path = _db_path()
    with sqlite3.connect(path) as conn:
        init_db_table(conn)
        conn.execute("DELETE FROM score_history_4h")
        for row in rows:
            csv_row = row_to_csv_dict(row)
            sym = compute_symbol_scores_at(
                datetime.strptime(csv_row["fetch_time"], "%Y-%m-%d %H:%M:%S")
            )
            btc = sym["BTC"]
            eth = sym["ETH"]
            sol = sym["SOL"]
            us = compute_us_score_from_row(csv_row) or sym["BTC"]
            conn.execute(
                """
                INSERT OR REPLACE INTO score_history_4h(
                    fetch_time, total_score, rating,
                    macro, regulation, funding, fundamentals,
                    btc_score, eth_score, sol_score, us_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    csv_row["fetch_time"],
                    float(csv_row["total_score"]),
                    csv_row["rating"],
                    float(csv_row["macro"]),
                    float(csv_row["regulation"]),
                    float(csv_row["funding"]),
                    float(csv_row["fundamentals"]),
                    btc,
                    eth,
                    sol,
                    us,
                ),
            )
        conn.commit()
    logger.info("已写入 market.db → score_history_4h（%d 条）", len(rows))
    return len(rows)


def write_csv(rows: list[dict], *, backup: bool = True) -> Path:
    log_dir = _log_dir()
    target = log_dir / SCORE_LOG_FILENAME
    if backup and target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = log_dir / f"score_history.csv.bak_{stamp}"
        shutil.copy2(target, bak)
        logger.info("已备份原 CSV → %s", bak.name)

    with open(target, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_SCORE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row_to_csv_dict(row))
    logger.info("已写入 %s（%d 条）", target, len(rows))
    return target


def build_history(
    *,
    start_date: str,
    end_date: str | None,
    prefer_existing: bool = True,
) -> list[dict]:
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59)
        if end_date
        else datetime.now()
    )
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    ensure_prices(start_date, end_dt.strftime("%Y-%m-%d"))

    existing = load_existing_buckets(start_date) if prefer_existing else {}
    slots = iter_4h_slots(start_dt, end_dt)

    out: list[dict] = []
    reused = 0
    generated = 0

    for slot in slots:
        if prefer_existing and slot in existing:
            ex = existing[slot]
            try:
                row = {
                    "fetch_time": _fmt_ts(slot),
                    "total_score": float(ex.get("total_score") or 0),
                    "rating": ex.get("rating") or "中性",
                    "macro": float(ex.get("macro") or WEIGHT_MACRO * 0.5),
                    "regulation": float(ex.get("regulation") or WEIGHT_REGULATION * 0.5),
                    "funding": float(ex.get("funding") or WEIGHT_FUNDING * 0.5),
                    "fundamentals": float(
                        ex.get("fundamentals") or WEIGHT_FUNDAMENTALS * 0.5
                    ),
                }
                reused += 1
            except (TypeError, ValueError):
                row = compute_scores_at(slot)
                generated += 1
        else:
            row = compute_scores_at(slot)
            generated += 1
        out.append(row)

    logger.info(
        "时间槽 %d 个 · 保留已有桶 %d · 新生成 %d",
        len(slots),
        reused,
        generated,
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="补全 2025 年起每 4 小时晴雨表分数历史")
    parser.add_argument("--start", default=DEFAULT_START, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD（默认今天）")
    parser.add_argument(
        "--no-prefer-existing",
        action="store_true",
        help="不保留 CSV 已有记录，全部按价格重新生成",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    rows = build_history(
        start_date=args.start,
        end_date=args.end,
        prefer_existing=not args.no_prefer_existing,
    )

    if not rows:
        logger.error("未生成任何记录，请检查价格回填是否成功")
        return 1

    if args.dry_run:
        logger.info("dry-run：将写入 %d 条（首条 %s 总分 %.1f）", len(rows), rows[0]["fetch_time"], rows[0]["total_score"])
        logger.info("dry-run：末条 %s 总分 %.1f", rows[-1]["fetch_time"], rows[-1]["total_score"])
        return 0

    write_csv(rows)
    write_market_db(rows)

    logger.info("完成。请刷新网页并切换 BTC/ETH/SOL/美股大盘 查看折线图。")
    logger.info("API: GET /api/score-history?since=%s", args.start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
