#!/usr/bin/env python3
"""
回填近 90 天 4h 品种 raw 分与百分位归一历史（供实时百分位窗口）。

用法（项目根目录）：
    python build_symbol_raw_history.py
    python build_symbol_raw_history.py --days 90 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoring.symbol_scores import compute_normalized_scores_chronological

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("build_symbol_raw_history")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    end = datetime.now()
    start = end - timedelta(days=args.days)
    slots = iter_4h_slots(start, end)
    logger.info("回填 %d 个 4h 槽位 (%s ~ %s)", len(slots), start.date(), end.date())

    if args.dry_run:
        sample = compute_normalized_scores_chronological(
            slots[:48], persist=False
        )
        first_ts = next(iter(sample))
        logger.info("dry-run 样本 %s: %s", first_ts, sample[first_ts])
        return

    result = compute_normalized_scores_chronological(slots, persist=True)
    logger.info("已写入 %d 条时间戳", len(result))


if __name__ == "__main__":
    main()
