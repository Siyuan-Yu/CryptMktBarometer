"""
全球监管政策分项计分（满分 20）
汇总监管相关资讯的单条影响分。
"""

from __future__ import annotations

from collectors.types import NewsItem
from scoring.constants import REGULATION_KEYWORDS, WEIGHT_REGULATION
from scoring.utils import avg_impact, filter_news_by_keywords, map_impact_to_points, top_impact_sum


def score_regulation(all_news: list[NewsItem]) -> tuple[float, str]:
    max_pts = WEIGHT_REGULATION
    reg_news = filter_news_by_keywords(all_news, REGULATION_KEYWORDS)

    if not reg_news:
        # 无监管类命中时，用全市场资讯均值弱参考，避免长期钉死在 10 分
        if all_news:
            blended = top_impact_sum(all_news, n=3) * 0.35
            score = map_impact_to_points(blended, max_pts)
            return round(score, 1), f"无监管关键词命中，参考全市场重磅(弱权重)，均影响{blended:+.1f}"

        return round(max_pts * 0.5, 1), "无监管类资讯，中性"

    heavy = top_impact_sum(reg_news, n=5)
    mean = avg_impact(reg_news)
    blended_impact = heavy * 0.65 + mean * 0.35
    score = map_impact_to_points(blended_impact, max_pts)

    pos = sum(1 for n in reg_news if n.impact_score > 0)
    neg = sum(1 for n in reg_news if n.impact_score < 0)
    summary = (
        f"监管相关 {len(reg_news)} 条，利多{pos}/利空{neg}，"
        f"重磅均值{heavy:+.1f}，综合影响{blended_impact:+.1f}"
    )
    return round(score, 1), summary
