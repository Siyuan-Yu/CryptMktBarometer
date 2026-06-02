"""
市场评级标签工具
根据综合总分（0~100）返回评级文案，供前端展示。
"""


def rating_from_total_score(total: float) -> str:
    """
    总分区间规则：
    >70 强利多 | 55~70 偏利多 | 45~55 中性 | 30~45 偏利空 | <30 强利空
    """
    if total > 70:
        return "强利多"
    if total >= 55:
        return "偏利多"
    if total >= 45:
        return "中性"
    if total >= 30:
        return "偏利空"
    return "强利空"


def rating_css_class(total: float) -> str:
    """返回与评级对应的 CSS 类名，便于着色。"""
    if total > 70:
        return "rating-bull-strong"
    if total >= 55:
        return "rating-bull"
    if total >= 45:
        return "rating-neutral"
    if total >= 30:
        return "rating-bear"
    return "rating-bear-strong"
