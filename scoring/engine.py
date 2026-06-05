"""
晴雨计分总引擎
汇总宏观 / 监管 / 资金 / 基本面四分项，计算综合总分（0~100）。
"""

from __future__ import annotations

from typing import Any

from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from collectors.news_recency import filter_recent_news
from collectors.types import NewsItem
from scoring.utils import clamp
from scoring.community_score import apply_community_to_total
from storage.onchain_db import get_latest_snapshot
from core.market_rating import rating_from_total_score
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from core.config_loader import load_config
from scoring.fundamentals_score import score_fundamentals
from scoring.funding_score import score_funding
from scoring.macro_score import score_macro
from scoring.regulation_score import score_regulation

from scoring.result import ScoreResult


def compute_scores(
    *,
    macro: MacroSnapshot,
    funding: FundingSnapshot,
    all_news: list[NewsItem],
    macro_data_summary: str,
    funding_data_summary: str,
    onchain_connected: bool = False,
    onchain_data_summary: str = "",
) -> ScoreResult:
    """
    执行完整计分并返回页面所需结构。
    """
    cfg = load_config()
    all_news = filter_recent_news(all_news, cfg=cfg)

    if cfg.get("scoring", {}).get("use_news_v2", True):
        from scoring.score_v2 import compute_scores_v2

        return compute_scores_v2(
            macro=macro,
            funding=funding,
            all_news=all_news,
            macro_data_summary=macro_data_summary,
            funding_data_summary=funding_data_summary,
            onchain_connected=onchain_connected,
            onchain_data_summary=onchain_data_summary,
        )

    macro_pts, macro_logic = score_macro(macro)
    reg_pts, reg_logic = score_regulation(all_news)
    fund_pts, fund_logic = score_funding(funding)
    funda_pts, funda_logic = score_fundamentals(
        all_news,
        onchain_connected=onchain_connected,
    )

    total = round(macro_pts + reg_pts + fund_pts + funda_pts, 1)
    onchain_snap = get_latest_snapshot()
    onchain_note = ""
    if onchain_snap:
        total = round(
            clamp(total + onchain_snap.adj_btc, 0.0, 100.0),
            1,
        )
        fund_pts = round(
            clamp(fund_pts + onchain_snap.adj_market * 0.6, 0.0, WEIGHT_FUNDING),
            1,
        )
        funda_pts = round(
            clamp(
                funda_pts + (onchain_snap.adj_eth + onchain_snap.adj_sol) * 0.15,
                0.0,
                WEIGHT_FUNDAMENTALS,
            ),
            1,
        )
        onchain_note = f"｜链上客观{onchain_snap.summary[:80]}"
    total = min(100.0, max(0.0, total))
    total = apply_community_to_total(total)
    rating = rating_from_total_score(total)

    categories = [
        {
            "name": "宏观数据",
            "weight": WEIGHT_MACRO,
            "score": macro_pts,
            "summary": f"{macro_data_summary}｜计分：{macro_logic}",
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
            "summary": f"{funding_data_summary}｜计分：{fund_logic}{onchain_note}",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": WEIGHT_FUNDAMENTALS,
            "score": funda_pts,
            "summary": (
                f"{onchain_data_summary}｜计分：{funda_logic}{onchain_note}"
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
