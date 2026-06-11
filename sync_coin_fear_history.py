#!/usr/bin/env python3
"""回填 BTC/ETH/SOL 每日币种恐慌（CFGI 或价格代理）。"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.coin_fear_collect import backfill_daily_range

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("sync_coin_fear_history")

SYMBOLS = ("BTC", "ETH", "SOL")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()
    end = args.end or datetime.now().strftime("%Y-%m-%d")
    total = 0
    for sym in SYMBOLS:
        n = backfill_daily_range(sym, start_date=args.start, end_date=end)
        logger.info("%s: %d 天", sym, n)
        total += n
    logger.info("完成，共写入 %d 条日记录", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
