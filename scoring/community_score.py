"""
社区舆情低权重叠加：单车道最多 ±2，全市场弱参考 ±0.5。
"""

from __future__ import annotations

from collectors.community_sentiment import LaneSentiment
from scoring.utils import clamp
from storage.community_db import load_latest_snapshot

_LANE_CAP = 2.0
_MARKET_CAP = 0.8


def apply_community_to_scores(
    scores: dict[str, float],
    lanes: dict[str, LaneSentiment] | None = None,
) -> dict[str, float]:
    if lanes is None:
        lanes = load_latest_snapshot()
    if not lanes:
        return scores
    out = dict(scores)
    mapping = {"BTC": "btc", "ETH": "eth", "SOL": "sol"}
    for sym, key in mapping.items():
        if sym not in out or key not in lanes:
            continue
        adj = clamp(lanes[key].aggregate_impact, -_LANE_CAP, _LANE_CAP)
        out[sym] = round(clamp(out[sym] + adj, 0.0, 100.0), 1)
    return out


def apply_community_to_total(total: float, lanes: dict[str, LaneSentiment] | None = None) -> float:
    if lanes is None:
        lanes = load_latest_snapshot()
    if not lanes:
        return total
    avg = sum(s.aggregate_impact for s in lanes.values()) / max(len(lanes), 1)
    adj = clamp(avg * 0.35, -_MARKET_CAP, _MARKET_CAP)
    return round(clamp(total + adj, 0.0, 100.0), 1)
