"""
各资讯源独立关键词过滤（配合车道隔离，不新增数据库字段）。
feed_key 写入 NewsItem.raw["feed_key"]。
"""

from __future__ import annotations

import re

from collectors.types import NewsItem

# BTC 专属
_BTC_FEED = re.compile(
    r"\b(bitcoin|\bbtc\b|\$btc|satosh|halving|hashrate|miner|mining|"
    r"gbtc|grayscale|ark invest|ark\b|bitcoin core|core dev|taproot|"
    r"spot btc|btc etf|microstrategy|mstr|灰度|比特币|减半|矿工)\b",
    re.I,
)

# ETH 专属
_ETH_FEED = re.compile(
    r"\b(ethereum|\beth\b|\$eth|eip[- ]?\d+|erc-?20|staking|beacon|"
    r"layer.?2|\bl2\b|arbitrum|optimism|rollup|bankless|defi|uniswap|"
    r"vitalik|gas fee|eth etf|consensys|以太坊|质押|提款)\b",
    re.I,
)

# SOL 专属
_SOL_FEED = re.compile(
    r"\b(solana|\bsol\b|\$sol|jupiter|marinade|jito|raydium|phantom|"
    r"fantom|ftm\b|bonk|validator|firedancer|solana foundation|"
    r"pay\.sh|mainnet upgrade|solana ecosystem)\b",
    re.I,
)

# Blockworks：美联储 + 美股宏观
_BLOCKWORKS = re.compile(
    r"\b(fed|fomc|powell|rate cut|rate hike|cpi|ppi|pce|nonfarm|nfp|"
    r"inflation|treasury|yield|s&p|nasdaq|dow|wall street|stock market|"
    r"earnings|gdp|recession|macro|policy|美联储|加息|降息|非农|通胀|美股)\b",
    re.I,
)

# Decrypt / CT：全球监管与政策
_REG_POLICY = re.compile(
    r"\b(sec|cftc|regulat|legislat|bill|enforcement|lawsuit|ban\b|"
    r"approved|approval|etf|congress|senate|compliance|policy|"
    r"监管|法案|起诉|获批|etf|证监会)\b",
    re.I,
)

FEED_KEYWORD_RULES: dict[str, re.Pattern[str]] = {
    "bitcoin_magazine": _BTC_FEED,
    "bitcoin_core": _BTC_FEED,
    "grayscale": _BTC_FEED,
    "ark_invest": _BTC_FEED,
    "coindesk": _BTC_FEED,
    "bankless": _ETH_FEED,
    "the_defiant": _ETH_FEED,
    "ethereum_blog": _ETH_FEED,
    "ethereum_magicians": _ETH_FEED,
    "ethresearch": _ETH_FEED,
    "optimism_gov": _ETH_FEED,
    "cointelegraph_arbitrum": _ETH_FEED,
    "cointelegraph_optimism": _ETH_FEED,
    "theblock": _ETH_FEED,
    "solana": _SOL_FEED,
    "solana_blog": _SOL_FEED,
    "solana_status": _SOL_FEED,
    "marinade": _SOL_FEED,
    "cointelegraph_sol": _SOL_FEED,
    "cointelegraph_fantom": _SOL_FEED,
    "blockworks": _BLOCKWORKS,
    "decrypt": _REG_POLICY,
    "cointelegraph_policy": _REG_POLICY,
}

LANE_FEED_KEYS: dict[str, frozenset[str]] = {
    "btc": frozenset(
        {
            "bitcoin_magazine",
            "bitcoin_core",
            "grayscale",
            "ark_invest",
            "coindesk",
        }
    ),
    "eth": frozenset(
        {
            "bankless",
            "the_defiant",
            "ethereum_blog",
            "ethereum_magicians",
            "ethresearch",
            "optimism_gov",
            "cointelegraph_arbitrum",
            "cointelegraph_optimism",
            "theblock",
        }
    ),
    "sol": frozenset(
        {
            "solana",
            "solana_blog",
            "solana_status",
            "marinade",
            "cointelegraph_sol",
            "cointelegraph_fantom",
        }
    ),
    "macro": frozenset({"blockworks", "decrypt", "cointelegraph_policy"}),
}


def _item_text(item: NewsItem) -> str:
    return f"{item.title} {item.source} {' '.join(item.keywords)}".lower()


def matches_feed_keywords(item: NewsItem, feed_key: str, lane: str) -> bool:
    """源内关键词命中，或该源为本车道权威源且标题含车道核心词。"""
    pat = FEED_KEYWORD_RULES.get(feed_key)
    if not pat:
        return True
    text = _item_text(item)
    if pat.search(text):
        return True
    if feed_key in LANE_FEED_KEYS.get(lane, frozenset()):
        if lane == "btc" and re.search(r"\b(bitcoin|btc|比特币)\b", text, re.I):
            return True
        if lane == "eth" and re.search(r"\b(ethereum|eth|以太坊)\b", text, re.I):
            return True
        if lane == "sol" and re.search(r"\b(solana|sol)\b", text, re.I):
            return True
    return False


def filter_by_feed_keywords(items: list[NewsItem], lane: str) -> list[NewsItem]:
    kept: list[NewsItem] = []
    for it in items:
        fk = (it.raw or {}).get("feed_key") or ""
        if not fk or fk not in FEED_KEYWORD_RULES:
            kept.append(it)
            continue
        if matches_feed_keywords(it, fk, lane):
            kept.append(it)
    return kept
