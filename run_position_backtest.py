#!/usr/bin/env python3
"""
仓位策略 4H 全量回测（含单币种恐慌加减分后的 score）。

规则：
- 空仓：score≥55 开多；score≤45 开空
- 持多：仅下周期分数下降时平仓；否则继续持有
- 持空：仅下周期分数上升时平仓；否则继续持有
- 持仓中禁止新开仓

输出：new_backtest_4h_strategy.csv（项目根目录）
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_loader import PROJECT_ROOT
from scoring.multi_asset import SIGNAL_LONG_THRESHOLD, SIGNAL_SHORT_THRESHOLD, signal_from_score
from scoring.symbol_scores import compute_normalized_scores_chronological
from storage import price_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("position_backtest")

EXPORT_FILE = "new_backtest_4h_strategy.csv"
COLUMNS = (
    "time",
    "symbol",
    "score",
    "signal",
    "position",
    "action",
    "close_price",
)
SYMBOLS = ("BTC", "ETH", "SOL")


def _bucket_4h(dt: datetime) -> datetime:
    return dt.replace(
        hour=(dt.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def iter_4h_slots(start: datetime, end: datetime) -> list[datetime]:
    cur = _bucket_4h(start)
    end_b = _bucket_4h(end)
    slots: list[datetime] = []
    while cur <= end_b:
        slots.append(cur)
        cur += timedelta(hours=4)
    return slots


def simulate_positions(
    slots: list[datetime],
    norm_by_ts: dict[str, dict[str, float]],
) -> list[dict]:
    rows: list[dict] = []
    state: dict[str, str] = {s: "flat" for s in SYMBOLS}
    prev_score: dict[str, float | None] = {s: None for s in SYMBOLS}

    for slot in slots:
        ts = slot.strftime("%Y-%m-%d %H:%M:%S")
        sym_scores = norm_by_ts.get(ts, {})
        for symbol in SYMBOLS:
            score = float(sym_scores.get(symbol, 50.0))
            close = price_db.get_close_at(symbol, slot)
            pos = state[symbol]
            prev = prev_score[symbol]
            action = "hold"

            if pos == "flat":
                if score >= SIGNAL_LONG_THRESHOLD:
                    pos = "long"
                    action = "open_long"
                elif score <= SIGNAL_SHORT_THRESHOLD:
                    pos = "short"
                    action = "open_short"
            elif pos == "long":
                if prev is not None and score < prev:
                    pos = "flat"
                    action = "reduce_long"
            elif pos == "short":
                if prev is not None and score > prev:
                    pos = "flat"
                    action = "reduce_short"

            state[symbol] = pos
            prev_score[symbol] = score
            rows.append(
                {
                    "time": ts,
                    "symbol": symbol,
                    "score": round(score, 1),
                    "signal": signal_from_score(score),
                    "position": pos,
                    "action": action,
                    "close_price": round(close, 8) if close is not None else "",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--skip-price-backfill", action="store_true")
    args = parser.parse_args()

    end_dt = (
        datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59)
        if args.end
        else datetime.now()
    )
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")

    if not args.skip_price_backfill:
        from export_new_backtest_4h import ensure_hourly_prices

        ensure_hourly_prices(args.start, end_dt.strftime("%Y-%m-%d"))

    from collectors.coin_fear_collect import backfill_daily_range
    from collectors.market_fear_collect import backfill_range as backfill_market_fear

    end_day = end_dt.strftime("%Y-%m-%d")
    backfill_market_fear(start_date=args.start, end_date=end_day)
    for sym in SYMBOLS:
        backfill_daily_range(sym, start_date=args.start, end_date=end_day)

    slots = iter_4h_slots(start_dt, end_dt)
    logger.info("重算 %d 个 4h 分数槽位…", len(slots))
    norm_by_ts = compute_normalized_scores_chronological(slots, persist=False)
    rows = simulate_positions(slots, norm_by_ts)

    out = PROJECT_ROOT / EXPORT_FILE
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in COLUMNS})

    print(f"\n回测导出成功：{out.resolve()}")
    print(f"共 {len(rows)} 行（{len(slots)} 槽 × {len(SYMBOLS)} 品种）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
