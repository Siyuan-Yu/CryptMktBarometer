"""
资金链上数据分项计分（满分 25）
依据：CoinGlass 摘要、CoinGecko 全球市值变动等
"""

from __future__ import annotations

import re

from collectors.funding_collect import FundingSnapshot
from scoring.constants import WEIGHT_FUNDING
from scoring.utils import clamp, parse_signed_percent


def score_funding(snap: FundingSnapshot) -> tuple[float, str]:
    max_pts = WEIGHT_FUNDING
    score = max_pts * 0.5
    notes: list[str] = []

    for line in snap.summary_lines:
        lower = line.lower()

        pct = parse_signed_percent(line)
        if pct is not None and ("市值" in line or "market" in lower or "coingecko" in lower):
            if pct >= 3:
                delta = 8.0
            elif pct >= 1:
                delta = 4.0
            elif pct <= -3:
                delta = -8.0
            elif pct <= -1:
                delta = -4.0
            else:
                delta = pct * 1.2
            score += delta
            notes.append(f"全球市值24h {pct:+.2f}% → {delta:+.1f}分")
            continue

        if any(k in lower for k in ("净流入", "net inflow", "inflow")):
            score += 5.0
            notes.append("ETF/资金净流入信号")
        elif any(k in lower for k in ("净流出", "net outflow", "outflow")):
            score -= 5.0
            notes.append("ETF/资金净流出信号")

        if "爆仓" in line or "liquidation" in lower:
            m = re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?", lower)
            score -= 3.0
            notes.append("爆仓数据偏高，短线波动风险")

        if "持仓" in line or "open interest" in lower or "oi" in lower:
            if "+%" in line or "increase" in lower:
                score += 2.0
                notes.append("合约持仓上升，杠杆活跃度升")
            elif "-%" in line or "decrease" in lower:
                score -= 2.0
                notes.append("合约持仓下降")

    if "未配置" in " ".join(snap.summary_lines) and len(notes) == 0:
        notes.append("CoinGlass 未配置，主要依赖公开备用指标")

    if not snap.summary_lines:
        notes.append("资金面无数据，中性")

    score = round(clamp(score, 0.0, max_pts), 1)
    return score, "；".join(notes) if notes else "资金中性"
