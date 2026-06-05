"""
社区舆情：多空关键词识别、喊单/广告过滤、4h 同源同观点合并。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from collectors.news_recency import entry_published_at, parse_published_at

_SPAM = re.compile(
    r"(join my|dm me|whatsapp|telegram group|signal group|100x|guaranteed profit|"
    r"free airdrop|click here|register now|空投领取|带单|跟单群|私信|"
    r"广告|sponsored|promo code only)",
    re.I,
)

_BULL = re.compile(
    r"\b(bullish|bull|long\b|buy the dip|buying|accumulate|moon|pump|breakout|"
    r"看涨|做多|利多|看多|买入|抄底)\b",
    re.I,
)

_BEAR = re.compile(
    r"\b(bearish|bear|short\b|sell off|selling|dump|crash|rekt|"
    r"看跌|做空|利空|看空|卖出|爆仓)\b",
    re.I,
)


@dataclass
class CommunityPost:
    source: str
    lane: str
    title: str
    text: str
    url: str
    published_at: str
    feed_key: str = ""

    def full_text(self) -> str:
        return f"{self.title} {self.text}".strip()


@dataclass
class LaneSentiment:
    lane: str
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    merged_groups: int = 0
    spam_dropped: int = 0
    aggregate_impact: float = 0.0
    bullish_pct: float = 50.0
    summary: str = ""
    sources: dict[str, int] = field(default_factory=dict)


def is_spam(text: str) -> bool:
    return bool(_SPAM.search(text))


def classify_sentiment(text: str) -> str:
    """bull | bear | neutral"""
    if not text or is_spam(text):
        return "neutral"
    bull = len(_BULL.findall(text))
    bear = len(_BEAR.findall(text))
    if bull > bear and bull > 0:
        return "bull"
    if bear > bull and bear > 0:
        return "bear"
    return "neutral"


def _bucket_4h(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hour = (dt.hour // 4) * 4
    return dt.replace(hour=hour).isoformat()


def _viewpoint_fingerprint(text: str) -> str:
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text.lower())
    words = sorted({w for w in t.split() if len(w) > 2})[:10]
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:14]


def merge_posts_4h(posts: list[CommunityPost]) -> tuple[list[CommunityPost], int]:
    """
    同源同观点 4h 内合并为 1 条代表（保留最新一条文本，情绪取众数）。
    返回 (合并后列表, 被合并掉的条数)
    """
    groups: dict[tuple[str, str, str], list[CommunityPost]] = {}
    for p in posts:
        pub = parse_published_at(p.published_at)
        if pub is None:
            pub = datetime.now(timezone.utc)
        bucket = _bucket_4h(pub)
        fp = _viewpoint_fingerprint(p.full_text())
        key = (p.source, bucket, fp)
        groups.setdefault(key, []).append(p)

    merged: list[CommunityPost] = []
    dropped = 0
    for key, batch in groups.items():
        if len(batch) > 1:
            dropped += len(batch) - 1
        rep = batch[0]
        votes = [classify_sentiment(x.full_text()) for x in batch]
        bull = votes.count("bull")
        bear = votes.count("bear")
        if bull >= bear and bull > 0:
            label = "bull"
        elif bear > bull and bear > 0:
            label = "bear"
        else:
            label = "neutral"
        rep.text = (rep.text or "") + f" [4h合并{len(batch)}条·{label}]"
        merged.append(rep)
    return merged, dropped


def lane_impact_from_posts(posts: list[CommunityPost]) -> LaneSentiment:
    """汇总车道舆情 → 整体 ±0.3~2（不按单帖主导）。"""
    lane = posts[0].lane if posts else ""
    sent = LaneSentiment(lane=lane)
    if not posts:
        sent.summary = "无社区样本"
        return sent

    merged, dropped = merge_posts_4h(posts)
    sent.merged_groups = len(merged)
    sent.spam_dropped = dropped

    for p in merged:
        if is_spam(p.full_text()):
            sent.spam_dropped += 1
            continue
        label = classify_sentiment(p.full_text())
        sent.sources[p.source] = sent.sources.get(p.source, 0) + 1
        if label == "bull":
            sent.bullish += 1
        elif label == "bear":
            sent.bearish += 1
        else:
            sent.neutral += 1

    total = sent.bullish + sent.bearish + sent.neutral
    if total == 0:
        sent.aggregate_impact = 0.0
        sent.summary = "社区样本已过滤"
        return sent

    sent.bullish_pct = round(sent.bullish / total * 100.0, 1)
    ratio = (sent.bullish - sent.bearish) / max(total, 1)
    raw = ratio * 2.0
    if abs(raw) < 0.3 and raw != 0:
        raw = 0.3 if raw > 0 else -0.3
    sent.aggregate_impact = round(max(-2.0, min(2.0, raw)), 2)
    sent.summary = (
        f"社区{total}组(合并后)·多{sent.bullish}/空{sent.bearish}/中{sent.neutral} "
        f"→ {sent.aggregate_impact:+.2f}"
    )
    return sent
