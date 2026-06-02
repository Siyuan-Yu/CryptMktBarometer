"""
资讯分类过滤：SOL / ETH / 美股宏观 独立 TOP 列表
各分类互不混杂，仅展示与该类强相关的消息。
"""

from __future__ import annotations

import re
from typing import Any

from collectors.types import NewsItem

# SOL 专属（Solana 生态）
_SOL_PATTERNS = re.compile(
    r"\b(solana|\bsol\b|\$sol|jito|raydium|marinade|phantom wallet|"
    r"solana foundation|firedancer|saga phone|bonk|wif on sol)\b",
    re.I,
)

# ETH 专属（以太坊生态）
_ETH_PATTERNS = re.compile(
    r"\b(ethereum|\beth\b|\$eth|ether\b|eip-\d+|erc-20|erc20|"
    r"layer.?2|l2\b|arbitrum|optimism|base chain|staking reward|"
    r"beacon chain|vitalik|gas fee)\b",
    re.I,
)

# 美股 / 宏观
_MACRO_PATTERNS = re.compile(
    r"\b(cpi|ppi|core pce|nonfarm|nfp|jobs report|unemployment|"
    r"federal reserve|\bfed\b|fomc|powell|rate cut|rate hike|interest rate|"
    r"inflation|treasury yield|10-year|10y yield|bond yield|"
    r"s&p 500|s&p500|nasdaq|dow jones|wall street|stock market|"
    r"gdp|recession|dollar index|dxy|国债|非农|美联储|加息|降息|通胀|"
    r"美股|标普|纳斯达克|道琼斯)\b",
    re.I,
)

# 纯 BTC 且无 SOL/ETH 关键词时，不进入币种专属栏
_BTC_ONLY = re.compile(r"\b(bitcoin|\bbtc\b|\$btc)\b", re.I)


def _item_text(item: NewsItem) -> str:
    parts = [item.title, item.logic, " ".join(item.keywords)]
    raw_title = (item.raw or {}).get("title") or ""
    if raw_title and raw_title not in parts[0]:
        parts.append(raw_title)
    return " ".join(p for p in parts if p).lower()


def is_sol_related(item: NewsItem) -> bool:
    text = _item_text(item)
    if not _SOL_PATTERNS.search(text):
        return False
    # 宏观类消息若仅顺带提及 SOL，仍归宏观（优先宏观独占）
    if is_macro_related(item) and not re.search(
        r"\b(solana|\bsol\b|\$sol)\b", text, re.I
    ):
        return False
    return True


def is_eth_related(item: NewsItem) -> bool:
    text = _item_text(item)
    if not _ETH_PATTERNS.search(text):
        return False
    if is_macro_related(item) and not re.search(
        r"\b(ethereum|\beth\b|\$eth)\b", text, re.I
    ):
        return False
    return True


def is_macro_related(item: NewsItem) -> bool:
    return bool(_MACRO_PATTERNS.search(_item_text(item)))


def filter_by_category(items: list[NewsItem], category: str) -> list[NewsItem]:
    """category: sol | eth | macro"""
    if category == "sol":
        return [i for i in items if is_sol_related(i)]
    if category == "eth":
        return [i for i in items if is_eth_related(i)]
    if category == "macro":
        return [i for i in items if is_macro_related(i)]
    return []


def select_category_top(
    items: list[NewsItem],
    category: str,
    *,
    limit: int = 10,
    to_display,
) -> list[dict[str, Any]]:
    """按影响分绝对值排序，取分类 TOP N。"""
    filtered = filter_by_category(items, category)
    sorted_items = sorted(filtered, key=lambda x: abs(x.impact_score), reverse=True)
    return [to_display(n) for n in sorted_items[:limit]]
