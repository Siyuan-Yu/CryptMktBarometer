"""
资讯影响分预估（第三步临时规则，第四步将迁入 scoring 模块）
根据标题关键词与 CryptoPanic 社区投票估算正负分。
"""

from __future__ import annotations

import re

# 利多 / 利空 英文关键词（加密资讯以英文为主）
_BULLISH = (
    "etf approved",
    "approval",
    "rate cut",
    "dovish",
    "inflow",
    "surge",
    "rally",
    "breakout",
    "partnership",
    "adoption",
    "upgrade",
    "record high",
    "bullish",
    "launch",
    "listing",
)
_BEARISH = (
    "hack",
    "exploit",
    "lawsuit",
    "sec sue",
    "ban",
    "outflow",
    "crash",
    "plunge",
    "liquidation",
    "bankrupt",
    "delist",
    "investigation",
    "bearish",
    "sanction",
    "halt",
    "vulnerability",
)


def score_from_title(title: str) -> tuple[float, list[str], str]:
    """
    根据标题关键词给出临时影响分（-10 ~ +10）及命中词。
    """
    lower = title.lower()
    hit_bull = [k for k in _BULLISH if k in lower]
    hit_bear = [k for k in _BEARISH if k in lower]

    score = len(hit_bull) * 2.5 - len(hit_bear) * 2.5
    score = max(-10.0, min(10.0, score))

    keywords = (hit_bull + hit_bear)[:3]
    if not keywords:
        keywords = _extract_title_tokens(title, limit=3)

    if hit_bull and not hit_bear:
        logic = f"标题含利多倾向词：{', '.join(hit_bull[:3])}"
    elif hit_bear and not hit_bull:
        logic = f"标题含利空倾向词：{', '.join(hit_bear[:3])}"
    elif hit_bull or hit_bear:
        logic = "标题多空关键词并存，中性偏弱波动"
    else:
        logic = "标题未命中预设关键词，影响分接近中性"

    return score, keywords, logic


def score_from_cryptopanic_votes(votes: dict) -> float:
    """CryptoPanic 社区投票折算影响分。"""
    positive = int(votes.get("positive") or 0)
    negative = int(votes.get("negative") or 0)
    important = bool(votes.get("important"))
    score = (positive - negative) * 1.5
    if important:
        score += 3.0 if score >= 0 else -3.0
    return max(-10.0, min(10.0, score))


def merge_scores(title_score: float, extra: float) -> float:
    """合并标题分与其它信号，取加权平均后限幅。"""
    combined = title_score * 0.4 + extra * 0.6 if extra else title_score
    return max(-10.0, min(10.0, round(combined, 1)))


def _extract_title_tokens(title: str, limit: int = 3) -> list[str]:
    words = re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", title)
    seen: list[str] = []
    for w in words:
        u = w.upper() if w.isascii() else w
        if u not in seen and u.lower() not in {"the", "and", "for", "with"}:
            seen.append(u if w.isascii() else w)
        if len(seen) >= limit:
            break
    return seen[:limit]
