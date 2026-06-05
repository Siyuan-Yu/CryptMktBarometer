#!/usr/bin/env python3
"""
导出 new_backtest_4h.csv（新评分体系：60/30/10 分层 + 90 天百分位归一 + 历史链上/成交量/巨鲸/合约代理因子）

- 范围：2025-01-01 至今，4 小时粒度，BTC / ETH / SOL
- 字段：time,symbol,score,signal,close_price
- 信号：score≥55 多 | score≤45 空 | 其余 中性
- 全量重算写入 symbol_raw_scores 后导出（不改 UI / 折线图 / 旧 CSV）

用法：
    python export_new_backtest_4h.py
    python export_new_backtest_4h.py --skip-price-backfill
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
from storage.symbol_score_db import clear_scores_since

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("export_new_backtest_4h")

DEFAULT_START = "2025-01-01"
SYMBOLS = ("BTC", "ETH", "SOL")
EXPORT_FILE = "new_backtest_4h.csv"
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
    logger.info("小时 K 线不足，正在回填 %s ~ %s …", start_date, end_date)
    from collectors.price_hourly import backfill_history

    counts = backfill_history(list(SYMBOLS), start_date, end_date)
    for sym, n in counts.items():
        logger.info("  %s: %d 根", sym, n)


def full_rebuild_and_export(
    *,
    start_date: str,
    end_date: str | None,
) -> tuple[list[dict], Path]:
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59)
        if end_date
        else datetime.now()
    )
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    slots = iter_4h_slots(start_dt, end_dt)

    deleted = clear_scores_since(start_date)
    logger.info("已清空 symbol_raw_scores（%s 起）%d 条，开始全量重算…", start_date, deleted)

    t0 = time.time()
    norm_by_ts = compute_normalized_scores_chronological(slots, persist=True)
    logger.info("全量重算完成，%d 个 4h 槽位，耗时 %.0fs", len(slots), time.time() - t0)

    rows: list[dict] = []
    for slot in slots:
        ts = _fmt_time(slot)
        sym_scores = norm_by_ts.get(ts, {})
        for symbol in SYMBOLS:
            score = round(float(sym_scores.get(symbol, 50.0)), 1)
            close = price_db.get_close_at(symbol, slot)
            rows.append(
                {
                    "time": ts,
                    "symbol": symbol,
                    "score": score,
                    "signal": signal_from_score(score),
                    "close_price": round(close, 8) if close is not None else "",
                }
            )
    return rows, PROJECT_ROOT / EXPORT_FILE


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in COLUMNS})


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 new_backtest_4h.csv")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--skip-price-backfill", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    end_label = args.end or datetime.now().strftime("%Y-%m-%d")
    if not args.skip_price_backfill:
        ensure_hourly_prices(args.start, end_label)

    rows, out_path = full_rebuild_and_export(
        start_date=args.start,
        end_date=args.end,
    )
    if not rows:
        logger.error("未生成数据")
        return 1

    per_sym = len(rows) // len(SYMBOLS)
    logger.info(
        "共 %d 行（约 %d 时间槽 × %d 品种）",
        len(rows),
        per_sym,
        len(SYMBOLS),
    )

    if args.dry_run:
        logger.info("dry-run 首行: %s", rows[0])
        logger.info("dry-run 末行: %s", rows[-1])
        return 0

    write_csv(rows, out_path)
    print(f"\n导出成功：{out_path.resolve()}")
    print(f"共 {len(rows)} 行（{per_sym} 个 4h 时点 × {len(SYMBOLS)} 品种）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
