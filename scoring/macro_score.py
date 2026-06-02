"""
宏观数据分项计分（满分 40）
依据：美债10Y变动、政策预期文案、经济日历密度
"""

from __future__ import annotations

from collectors.macro_collect import MacroSnapshot
from scoring.constants import WEIGHT_MACRO
from scoring.utils import clamp


def score_macro(snap: MacroSnapshot) -> tuple[float, str]:
    """
    宏观分项得分 0~40。
    中性起点 20 分，根据利率路径与数据可得性加减。
    """
    max_pts = WEIGHT_MACRO
    score = max_pts * 0.5
    notes: list[str] = []

    # 10Y 收益率变动：上行压制风险资产，下行偏利好
    if snap.treasury_10y_chg_bps is not None:
        bps = snap.treasury_10y_chg_bps
        if bps >= 8:
            delta = -12.0
        elif bps >= 3:
            delta = -6.0
        elif bps <= -8:
            delta = 12.0
        elif bps <= -3:
            delta = 6.0
        else:
            delta = -bps * 0.8
        score += delta
        notes.append(f"10Y较前日{bps:+.0f}bp，调整{delta:+.1f}分")

    if snap.treasury_10y is not None and snap.treasury_10y_chg_bps is None:
        notes.append(f"10Y现值{snap.treasury_10y:.2f}%（暂无前日对比）")

    # 政策预期 proxy 文案
    if snap.fed_expectation:
        text = snap.fed_expectation
        if any(k in text for k in ("倒挂", "降息", "衰退", "dovish")):
            score += 5.0
            notes.append("政策预期偏鸽/降息")
        elif any(k in text for k in ("平稳", "正常", "neutral")):
            score += 2.0
            notes.append("政策预期平稳")
        elif any(k in text for k in ("hawkish", "加息", "紧缩")):
            score -= 4.0
            notes.append("政策预期偏鹰")

    # 近期经济数据发布密集 → 短期不确定性略升
    cal_n = len(snap.calendar_hints)
    if cal_n >= 6:
        score -= 3.0
        notes.append(f"近期宏观发布较密({cal_n}项)，略降分")
    elif cal_n >= 1:
        notes.append(f"近期宏观发布{cal_n}项")

    if not snap.treasury_10y and not snap.fed_expectation and cal_n == 0:
        notes.append("宏观指标不足，维持中性")

    score = round(clamp(score, 0.0, max_pts), 1)
    summary = "；".join(notes) if notes else "宏观中性"
    return score, summary
