#!/usr/bin/env python3
"""
独立回测数据导出脚本（不修改项目内任何已有源码文件）

从 2025-01-01 00:00 至今，按每 4 小时（0/4/8/12/16/20 点）生成
BTC / ETH / SOL 晴雨表分数与收盘价，导出至项目根目录：

    backtest_4h_data.csv

字段：time, symbol, score, signal, close_price

- 分项计分：与 scoring/engine + score_macro / score_funding 等正式模块一致
- 品种分数：与 core/score_history._score_from_row 一致（与网页折线图算法相同）
- 信号：score>=55 多 | score<=45 空 | 其余 中性（与 multi_asset 一致）
- 仅读取/可选回填 market.db 小时 K 线（不写 score_history.csv，不改前端数据源）

用法（项目根目录）：
    python export_backtest_data.py
    python export_backtest_data.py --dry-run
    python export_backtest_data.py --skip-price-backfill
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_loader import PROJECT_ROOT
from scoring.multi_asset import signal_from_score
from scoring.symbol_scores import compute_normalized_scores_chronological
from storage import price_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("export_backtest_data")

DEFAULT_START = "2025-01-01"
SYMBOLS = ("BTC", "ETH", "SOL")
EXPORT_FILE = "backtest_4h_data.csv"
COLUMNS = ("time", "symbol", "score", "signal", "close_price")
MIN_CANDLES = 8000


def _bucket_4h(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def iter_4h_slots(start: datetime, end: datetime) -> list[datetime]:
    cur = _bucket_4h(start)
    end_b = _bucket_4h(end)
    slots: list[datetime] = []
    while cur <= end_b:
        slots.append(cur)
        cur += timedelta(hours=4)
    return slots


def ensure_hourly_prices(start_date: str, end_date: str) -> None:
    price_db.init_schema()
    need = any(price_db.count_candles(s) < MIN_CANDLES for s in SYMBOLS)
    if not need:
        logger.info("market.db 小时 K 线充足，跳过回填")
        return
    logger.info(
        "小时 K 线不足，正在回填 %s ~ %s（仅 prices_hourly 表，不写 score_history）…",
        start_date,
        end_date,
    )
    from collectors.price_hourly import backfill_history

    counts = backfill_history(list(SYMBOLS), start_date, end_date)
    for sym, n in counts.items():
        logger.info("  %s: %d 根", sym, n)


def build_export_rows(
    *,
    start_date: str,
    end_date: str | None,
) -> list[dict[str, str | float]]:
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59)
        if end_date
        else datetime.now()
    )
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    slots = iter_4h_slots(start_dt, end_dt)

    rows: list[dict[str, str | float]] = []
    total_steps = len(slots)
    t0 = time.time()

    norm_by_ts = compute_normalized_scores_chronological(
        slots, persist=False
    )

    for i, slot in enumerate(slots):
        ts = _fmt_time(slot)
        sym_scores = norm_by_ts.get(ts, {})

        for symbol in SYMBOLS:
            score = sym_scores.get(symbol, 50.0)
            close = price_db.get_close_at(symbol, slot)
            rows.append(
                {
                    "time": _fmt_time(slot),
                    "symbol": symbol,
                    "score": score,
                    "signal": signal_from_score(score),
                    "close_price": round(close, 8) if close is not None else "",
                }
            )

        if (i + 1) % 200 == 0 or i + 1 == total_steps:
            elapsed = time.time() - t0
            logger.info("进度 %d / %d 时间槽 (%.0fs)", i + 1, total_steps, elapsed)

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "time": row["time"],
                    "symbol": row["symbol"],
                    "score": row["score"],
                    "signal": row["signal"],
                    "close_price": row["close_price"],
                }
            )
    logger.info("已导出 %s（%d 行）", path, len(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 4 小时粒度回测 CSV")
    parser.add_argument("--start", default=DEFAULT_START, help="起始 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束 YYYY-MM-DD，默认今天")
    parser.add_argument(
        "--skip-price-backfill",
        action="store_true",
        help="不自动回填 Binance K 线（需 market.db 已有足够数据）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计行数，不写文件")
    args = parser.parse_args()

    end_label = args.end or datetime.now().strftime("%Y-%m-%d")
    if not args.skip_price_backfill:
        ensure_hourly_prices(args.start, end_label)

    rows = build_export_rows(start_date=args.start, end_date=args.end)
    if not rows:
        logger.error("未生成数据，请检查 market.db 价格是否可用")
        return 1

    out_path = PROJECT_ROOT / EXPORT_FILE
    per_sym = len(rows) // len(SYMBOLS)
    logger.info(
        "共 %d 行（约 %d 个时间槽 × %d 品种）",
        len(rows),
        per_sym,
        len(SYMBOLS),
    )

    if args.dry_run:
        logger.info("dry-run 示例首行: %s", rows[0])
        logger.info("dry-run 示例末行: %s", rows[-1])
        return 0

    write_csv(rows, out_path)
    logger.info("完成。文件路径: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
