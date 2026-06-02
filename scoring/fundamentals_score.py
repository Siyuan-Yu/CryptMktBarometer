"""
ETH/SOL 币种基本面分项计分（满分 15）
依据：生态/质押/安全类资讯；链上 API 对接后可在 engine 中追加调整。
"""

from __future__ import annotations

from collectors.types import NewsItem
from scoring.constants import FUNDAMENTALS_KEYWORDS, WEIGHT_FUNDAMENTALS
from scoring.utils import (
    avg_impact,
    filter_news_by_keywords,
    map_impact_to_points,
    top_impact_sum,
)


def score_fundamentals(
    all_news: list[NewsItem],
    *,
    onchain_connected: bool = False,
) -> tuple[float, str]:
    max_pts = WEIGHT_FUNDAMENTALS
    eth_sol_news = filter_news_by_keywords(all_news, FUNDAMENTALS_KEYWORDS)

    if not eth_sol_news:
        base = max_pts * 0.5
        if onchain_connected:
            return round(base, 1), "链上指标已接入，本轮无相关资讯"
        return round(base, 1), "ETH/SOL 相关资讯未命中，链上 API 待对接，中性"

    heavy = top_impact_sum(eth_sol_news, n=5)
    mean = avg_impact(eth_sol_news)
    blended = heavy * 0.7 + mean * 0.3
    score = map_impact_to_points(blended, max_pts)

    hacks = sum(
        1
        for n in eth_sol_news
        if any(k in n.title.lower() for k in ("hack", "exploit", "漏洞", "attack"))
    )
    if hacks >= 2:
        score = max(0.0, score - 2.0)

    summary = (
        f"ETH/SOL 相关 {len(eth_sol_news)} 条，"
        f"重磅均值{heavy:+.1f}，安全事件{hacks}起"
    )
    if not onchain_connected:
        summary += "；链上质押/Dune 待接入"

    return round(score, 1), summary
