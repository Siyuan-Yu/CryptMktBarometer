"""
晴雨计分总引擎
汇总宏观 / 监管 / 资金 / 基本面四分项，计算综合总分（0~100）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from collectors.types import NewsItem
from core.market_rating import rating_from_total_score
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from scoring.fundamentals_score import score_fundamentals
from scoring.funding_score import score_funding
from scoring.macro_score import score_macro
from scoring.regulation_score import score_regulation


@dataclass
class ScoreResult:
    """一轮计分结果。"""

    total_score: float
    rating_label: str
    categories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def macro_summary(self) -> str:
        return self._cat_summary("宏观数据")

    def _cat_summary(self, name: str) -> str:
        for c in self.categories:
            if c.get("name") == name:
                return str(c.get("summary", ""))
        return ""


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
    macro_pts, macro_logic = score_macro(macro)
    reg_pts, reg_logic = score_regulation(all_news)
    fund_pts, fund_logic = score_funding(funding)
    funda_pts, funda_logic = score_fundamentals(
        all_news,
        onchain_connected=onchain_connected,
    )

    total = round(macro_pts + reg_pts + fund_pts + funda_pts, 1)
    total = min(100.0, max(0.0, total))
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
            "summary": f"{funding_data_summary}｜计分：{fund_logic}",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": WEIGHT_FUNDAMENTALS,
            "score": funda_pts,
            "summary": (
                f"{onchain_data_summary}｜计分：{funda_logic}"
                if onchain_data_summary
                else funda_logic
            ),
        },
    ]

    return ScoreResult(
        total_score=total,
        rating_label=rating,
        categories=categories,
    )
