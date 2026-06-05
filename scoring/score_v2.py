"""
晴雨表计分 V2（仅作用于新产生的实时分数，不改历史 CSV / backtest_4h_data.csv）

- 四大维度保留，资讯按车道/分级加权
- 宏观：全市场 35% 上限；单币视角在 score_history 层已处理
- 监管 33%、资金 28%、基本面余量
- 跨品种无关资讯权重折半或不计分
"""

from __future__ import annotations

from typing import Any

from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from collectors.news_categories import (
    is_btc_related,
    is_eth_related,
    is_macro_related,
    is_sol_related,
)
from collectors.types import NewsItem
from core.market_rating import rating_from_total_score
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from scoring.result import ScoreResult
from scoring.fundamentals_score import score_fundamentals
from scoring.funding_score import score_funding
from scoring.macro_score import score_macro
from scoring.regulation_score import score_regulation
from scoring.utils import avg_impact, clamp, map_impact_to_points, top_impact_sum
from scoring.community_score import apply_community_to_total
from storage.onchain_db import get_latest_snapshot

# 维度满分上限（与用户规则一致，合计 100）
_CAP_MACRO = 35.0
_CAP_REG = 33.0
_CAP_FUND = 28.0
_CAP_FUNDA = float(WEIGHT_FUNDAMENTALS)


def _tier_weight(item: NewsItem) -> float:
    tier = (item.raw or {}).get("news_tier", "normal")
    return {"major": 1.0, "normal": 0.55, "rumor": 0.15}.get(tier, 0.5)


def _lane_match(item: NewsItem, lane: str | None) -> float:
    """lane: btc | eth | sol | None(全市场)"""
    if lane is None:
        return 1.0
    if lane == "btc" and is_btc_related(item):
        return 1.0
    if lane == "eth" and is_eth_related(item):
        return 1.0
    if lane == "sol" and is_sol_related(item):
        return 1.0
    return 0.45  # 无关币种折半


def _weighted_impact_sum(items: list[NewsItem], n: int = 5, *, lane: str | None = None) -> float:
    if not items:
        return 0.0
    scored = []
    for it in items:
        w = _tier_weight(it) * _lane_match(it, lane)
        scored.append((abs(it.impact_score) * w, it.impact_score * w))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:n]
    if not top:
        return 0.0
    return sum(v for _, v in top) / len(top)


def score_regulation_v2(all_news: list[NewsItem]) -> tuple[float, str]:
    from scoring.constants import REGULATION_KEYWORDS
    from scoring.utils import filter_news_by_keywords

    reg_news = filter_news_by_keywords(all_news, REGULATION_KEYWORDS)
    if not reg_news:
        if all_news:
            blended = _weighted_impact_sum(all_news, n=3) * 0.25
            return round(map_impact_to_points(blended, _CAP_REG), 1), "监管弱参考"
        return round(_CAP_REG * 0.5, 1), "无监管类资讯"

    blended = _weighted_impact_sum(reg_news, n=6)
    pts = map_impact_to_points(blended, _CAP_REG)
    return round(clamp(pts, 0, _CAP_REG), 1), f"监管V2·{len(reg_news)}条·影响{blended:+.1f}"


def score_fundamentals_v2(
    all_news: list[NewsItem],
    *,
    onchain_connected: bool = False,
) -> tuple[float, str]:
    from scoring.constants import FUNDAMENTALS_KEYWORDS
    from scoring.utils import filter_news_by_keywords

    lane_news = [
        n
        for n in filter_news_by_keywords(all_news, FUNDAMENTALS_KEYWORDS)
        if is_btc_related(n) or is_eth_related(n) or is_sol_related(n)
    ]
    if not lane_news:
        return score_fundamentals(all_news, onchain_connected=onchain_connected)

    blended = _weighted_impact_sum(lane_news, n=5)
    pts = map_impact_to_points(blended, _CAP_FUNDA)
    return (
        round(clamp(pts, 0, _CAP_FUNDA), 1),
        f"基本面V2·标的匹配{len(lane_news)}条·{blended:+.1f}",
    )


def score_funding_v2(
    funding: FundingSnapshot,
    all_news: list[NewsItem],
) -> tuple[float, str]:
    base_pts, base_logic = score_funding(funding)
    onchain_news = [
        n
        for n in all_news
        if any(
            k in (n.title or "").lower()
            for k in ("inflow", "outflow", "etf", "持仓", "链上", "whale", "transfer")
        )
    ]
    if not onchain_news:
        return base_pts, base_logic

    extra = _weighted_impact_sum(onchain_news, n=4) * 0.35
    pts = clamp(base_pts + map_impact_to_points(extra, _CAP_FUND) * 0.25, 0, _CAP_FUND)
    return round(pts, 1), f"{base_logic}；链上资讯V2[{len(onchain_news)}条]"


def compute_scores_v2(
    *,
    macro: MacroSnapshot,
    funding: FundingSnapshot,
    all_news: list[NewsItem],
    macro_data_summary: str,
    funding_data_summary: str,
    onchain_connected: bool = False,
    onchain_data_summary: str = "",
) -> ScoreResult:
    macro_pts, macro_logic = score_macro(macro)
    macro_pts = round(clamp(macro_pts * (_CAP_MACRO / WEIGHT_MACRO), 0, _CAP_MACRO), 1)

    reg_pts, reg_logic = score_regulation_v2(all_news)
    fund_pts, fund_logic = score_funding_v2(funding, all_news)
    funda_pts, funda_logic = score_fundamentals_v2(
        all_news, onchain_connected=onchain_connected
    )

    total = round(macro_pts + reg_pts + fund_pts + funda_pts, 1)
    onchain_snap = get_latest_snapshot()
    onchain_note = ""
    if onchain_snap:
        total = round(clamp(total + onchain_snap.adj_btc, 0.0, 100.0), 1)
        fund_pts = round(
            clamp(fund_pts + onchain_snap.adj_market * 0.6, 0.0, _CAP_FUND),
            1,
        )
        funda_pts = round(
            clamp(
                funda_pts + (onchain_snap.adj_eth + onchain_snap.adj_sol) * 0.15,
                0.0,
                _CAP_FUNDA,
            ),
            1,
        )
        onchain_note = f"｜链上客观{onchain_snap.summary[:72]}"

    total = clamp(total, 0.0, 100.0)
    total = apply_community_to_total(total)
    rating = rating_from_total_score(total)

    categories = [
        {
            "name": "宏观数据",
            "weight": WEIGHT_MACRO,
            "score": macro_pts,
            "summary": f"{macro_data_summary}｜V2：{macro_logic}",
        },
        {
            "name": "全球监管政策",
            "weight": WEIGHT_REGULATION,
            "score": reg_pts,
            "summary": reg_logic,
        },
        {
            "name": "资金链上数据",
            "weight": WEIGHT_FUNDING,
            "score": fund_pts,
            "summary": f"{funding_data_summary}｜V2：{fund_logic}{onchain_note}",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": WEIGHT_FUNDAMENTALS,
            "score": funda_pts,
            "summary": (
                f"{onchain_data_summary}｜V2：{funda_logic}{onchain_note}"
                if onchain_data_summary
                else funda_logic + onchain_note
            ),
        },
    ]

    return ScoreResult(
        total_score=total,
        rating_label=rating,
        categories=categories,
    )
