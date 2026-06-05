"""
资讯分级影响分（V2）：重磅 ±8~12、普通 ±2~4、小道 ±0.5 以内。
供新一轮抓取计分使用，不改变历史 CSV。
"""

from __future__ import annotations

import re

from collectors.news_source_catalog import PREMIUM_AUTHORITY_FEED_KEYS
from collectors.news_quality import classify_news_tier, detect_source_tier
from collectors.news_impact import (
    merge_scores,
    score_from_cryptopanic_votes,
    score_from_macro_title,
    score_from_title,
)

_TIER_SCALE = {
    "major": (7.0, 12.0),
    "normal": (2.0, 4.0),
    "rumor": (0.2, 0.5),
}


def _clamp_signed(val: float, lo: float, hi: float) -> float:
    sign = 1.0 if val >= 0 else -1.0
    mag = max(lo, min(hi, abs(val)))
    return sign * mag


def apply_tier_to_impact(base_impact: float, tier: str) -> float:
    lo, hi = _TIER_SCALE.get(tier, _TIER_SCALE["normal"])
    if base_impact == 0:
        return 0.0
    return round(_clamp_signed(base_impact, lo, hi), 1)


def _resolve_tier(
    title: str,
    *,
    source_tier: str = "aggregate",
    feed_key: str = "",
) -> str:
    lower = title.lower()
    fk = feed_key or ""
    if fk in PREMIUM_AUTHORITY_FEED_KEYS and source_tier in ("official", "authority"):
        if re.search(
            r"\b(etf|sec|foundation|upgrade|halving|fomc|cpi|nonfarm|approved|"
            r"hack|launch|partnership|mainnet|staking|jupiter|marinade|"
            r"获批|升级|减半|监管|流入|流出)\b",
            lower,
            re.I,
        ):
            return "major"
        return "major"
    if re.search(
        r"\b(etf|sec|foundation|upgrade|halving|fomc|cpi|nonfarm|approved|hack)\b",
        lower,
        re.I,
    ):
        return "major"
    if source_tier in ("official", "authority"):
        return "normal"
    return "rumor" if detect_source_tier_from_title(title) == "aggregate" else "normal"


def score_from_title_v2(
    title: str,
    *,
    feed_type: str = "crypto",
    source_tier: str = "aggregate",
    feed_key: str = "",
) -> tuple[float, list[str], str]:
    if feed_type == "macro":
        impact, kw, logic = score_from_macro_title(title)
    else:
        impact, kw, logic = score_from_title(title)

    tier = _resolve_tier(title, source_tier=source_tier, feed_key=feed_key)
    scaled = apply_tier_to_impact(impact, tier)
    return scaled, kw, f"{logic}；分级[{tier}]→{scaled:+.1f}"


def detect_source_tier_from_title(title: str) -> str:
    if re.search(r"\b(sec|fed|foundation|official)\b", title, re.I):
        return "authority"
    return "aggregate"


def merge_scores_v2(title_score: float, extra: float, tier: str) -> float:
    combined = title_score * 0.35 + extra * 0.65 if extra else title_score
    return apply_tier_to_impact(combined, tier)
