"""
数据源分层计分：权威资讯 60% + 链上客观 30% + 社区舆情 10%。
小道消息通过 news_tier=rumor 降权，不进入权威层主路径。
"""

from __future__ import annotations

from datetime import datetime

from collectors.community_sentiment import LaneSentiment
from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from collectors.types import NewsItem
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from scoring.funding_score import score_funding
from scoring.macro_score import score_macro
from scoring.score_v2 import (
    score_fundamentals_v2,
    score_funding_v2,
    score_regulation_v2,
    _lane_match,
)
from scoring.utils import clamp
from storage.onchain_db import OnchainSnapshot

W_AUTHORITY = 0.60
W_ONCHAIN = 0.30
W_COMMUNITY = 0.10

_LANE_MAP = {"BTC": "btc", "ETH": "eth", "SOL": "sol"}


def _filter_authority_news(all_news: list[NewsItem], lane: str) -> list[NewsItem]:
    """权威层：剔除 rumor 级小道消息。"""
    out: list[NewsItem] = []
    for n in all_news:
        tier = (n.raw or {}).get("news_tier", "normal")
        if tier == "rumor":
            continue
        if _lane_match(n, lane) >= 0.45:
            out.append(n)
    return out


def score_authority_layer(
    symbol: str,
    *,
    all_news: list[NewsItem],
    macro: MacroSnapshot,
    funding: FundingSnapshot,
) -> float:
    """权威资讯层 → 0~100（宏观+监管+资金+车道基本面）。"""
    lane = _LANE_MAP.get(symbol, "btc")
    lane_news = _filter_authority_news(all_news, lane)

    macro_pts, _ = score_macro(macro)
    macro_scaled = macro_pts / WEIGHT_MACRO * 35.0 if WEIGHT_MACRO else 17.5

    if lane_news:
        reg_pts, _ = score_regulation_v2(lane_news)
        fund_pts, _ = score_funding_v2(funding, lane_news)
        funda_pts, _ = score_fundamentals_v2(lane_news)
    else:
        reg_pts = WEIGHT_REGULATION * 0.5
        fund_pts, _ = score_funding(funding)
        funda_pts = WEIGHT_FUNDAMENTALS * 0.5

    raw = macro_scaled * 0.22 + reg_pts * 0.28 + fund_pts * 0.32 + funda_pts * 0.18
    return round(clamp(raw, 0.0, 100.0), 1)


def score_onchain_layer(symbol: str, snap: OnchainSnapshot | None) -> float:
    """链上客观层 → 0~100（中性 50，按品种 adj 偏移）。"""
    if not snap:
        return 50.0
    key = _LANE_MAP.get(symbol, "btc")
    adj_map = {
        "btc": snap.adj_btc,
        "eth": snap.adj_eth,
        "sol": snap.adj_sol,
    }
    adj = adj_map.get(key, snap.adj_market)
    return round(clamp(50.0 + adj * 8.0, 0.0, 100.0), 1)


def score_community_layer(
    symbol: str,
    lanes: dict[str, LaneSentiment] | None,
) -> float:
    """社区/广场舆情层 → 0~100（中性 50）。"""
    if not lanes:
        return 50.0
    key = _LANE_MAP.get(symbol, "btc")
    lane = lanes.get(key)
    if not lane:
        return 50.0
    return round(clamp(50.0 + lane.aggregate_impact * 25.0, 0.0, 100.0), 1)


def composite_raw_score(
    symbol: str,
    *,
    all_news: list[NewsItem],
    macro: MacroSnapshot,
    funding: FundingSnapshot,
    onchain: OnchainSnapshot | None = None,
    community: dict[str, LaneSentiment] | None = None,
) -> tuple[float, float, float, float]:
    """
    返回 (raw_news, raw_onchain, raw_community, raw_composite)。
    """
    news = score_authority_layer(
        symbol, all_news=all_news, macro=macro, funding=funding
    )
    chain = score_onchain_layer(symbol, onchain)
    comm = score_community_layer(symbol, community)
    total = (
        news * W_AUTHORITY + chain * W_ONCHAIN + comm * W_COMMUNITY
    )
    return (
        round(news, 2),
        round(chain, 2),
        round(comm, 2),
        round(clamp(total, 0.0, 100.0), 2),
    )
