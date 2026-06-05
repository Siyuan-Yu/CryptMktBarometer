"""
社区类数据源汇总：Reddit / X / 币安广场 → 低权重舆情分（±0.3~2，不主导总分）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from collectors.community_binance import fetch_all_binance_square
from collectors.community_reddit import fetch_all_reddit
from collectors.community_sentiment import LaneSentiment, lane_impact_from_posts
from collectors.community_twitter import fetch_all_twitter
from core.config_loader import load_config
from storage.community_db import insert_community_snapshot, last_community_age_hours

logger = logging.getLogger(__name__)


@dataclass
class CommunityCollectResult:
    lanes: dict[str, LaneSentiment] = field(default_factory=dict)
    market_impact: float = 0.0
    skipped: bool = False
    errors: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.skipped and self.lanes:
            return "社区舆情(缓存) " + "；".join(s.summary for s in self.lanes.values())
        return "；".join(self.summary_lines) if self.summary_lines else "社区舆情未采集"


def _should_sync(cfg: dict) -> bool:
    hours = float(cfg.get("collector", {}).get("community_sync_hours", 4))
    age = last_community_age_hours()
    return age is None or age >= hours


def collect_community(*, force: bool = False) -> CommunityCollectResult:
    cfg = load_config()
    ds = cfg.get("data_sources", {}).get("community", {})
    if not any(
        ds.get(k, False)
        for k in ("reddit", "twitter", "binance_square")
    ):
        return CommunityCollectResult(skipped=True)

    if not force and not _should_sync(cfg):
        from storage.community_db import load_latest_snapshot

        cached = load_latest_snapshot()
        if cached:
            return CommunityCollectResult(
                lanes=cached,
                market_impact=sum(s.aggregate_impact for s in cached.values()) / max(
                    len(cached), 1
                ),
                skipped=True,
            )

    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))
    max_items = int(cfg.get("collector", {}).get("community_max_items", 25))
    errors: list[str] = []
    summary: list[str] = []
    by_lane_posts: dict[str, list] = {k: [] for k in ("btc", "eth", "sol")}

    if ds.get("reddit", True):
        posts, s, e = fetch_all_reddit(cfg, max_items=max_items, timeout=timeout)
        summary.extend(s)
        errors.extend(e)
        for p in posts:
            by_lane_posts.setdefault(p.lane, []).append(p)

    if ds.get("twitter", True):
        posts, s, e = fetch_all_twitter(cfg)
        summary.extend(s)
        errors.extend(e)
        for p in posts:
            by_lane_posts.setdefault(p.lane, []).append(p)

    if ds.get("binance_square", True):
        square, s, e = fetch_all_binance_square(cfg)
        summary.extend(s)
        errors.extend(e)
        for lane, posts in square.items():
            by_lane_posts.setdefault(lane, []).extend(posts)

    lanes: dict[str, LaneSentiment] = {}
    for lane in ("btc", "eth", "sol"):
        sent = lane_impact_from_posts(by_lane_posts.get(lane, []))
        sent.lane = lane
        lanes[lane] = sent

    market_impact = round(
        sum(s.aggregate_impact for s in lanes.values()) / max(len(lanes), 1),
        2,
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    insert_community_snapshot(now, lanes, market_impact, json.dumps(summary, ensure_ascii=False))

    logger.info(
        "社区舆情 %s | BTC%+s ETH%+s SOL%+s",
        now,
        lanes.get("btc", LaneSentiment("btc")).aggregate_impact,
        lanes.get("eth", LaneSentiment("eth")).aggregate_impact,
        lanes.get("sol", LaneSentiment("sol")).aggregate_impact,
    )
    return CommunityCollectResult(
        lanes=lanes,
        market_impact=market_impact,
        summary_lines=summary,
        errors=errors,
    )
