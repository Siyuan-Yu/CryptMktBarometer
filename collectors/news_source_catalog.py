"""
资讯源目录：按 BTC / ETH / SOL / 宏观 四车道隔离配置。
仅新增配置与元数据，不改变入库字段结构。
"""

from __future__ import annotations

from typing import Any

# (config_key, 展示名, 默认 RSS, asset_lane, source_tier)
# source_tier: official | authority | research | aggregate

BTC_FEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "btc", "authority"),
    (
        "bitcoin_magazine",
        "Bitcoin Magazine",
        "https://bitcoinmagazine.com/.rss/full/",
        "btc",
        "authority",
    ),
    (
        "bitcoin_core",
        "Bitcoin Core",
        "https://bitcoincore.org/en/rss.xml",
        "btc",
        "official",
    ),
    (
        "grayscale",
        "Grayscale",
        "https://grayscale.com/feed/",
        "btc",
        "official",
    ),
    ("ark_invest", "ARK Invest", "https://ark-funds.com/feed", "btc", "official"),
    (
        "sec_btc",
        "SEC·比特币ETF",
        "https://www.sec.gov/news/pressreleases.rss",
        "btc",
        "official",
    ),
    (
        "glassnode",
        "Glassnode",
        "https://insights.glassnode.com/rss/",
        "btc",
        "research",
    ),
)

ETH_FEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("theblock", "The Block", "https://www.theblock.co/rss.xml", "eth", "authority"),
    (
        "ethereum_blog",
        "以太坊基金会",
        "https://blog.ethereum.org/feed.xml",
        "eth",
        "official",
    ),
    ("bankless", "Bankless", "https://www.bankless.com/feed", "eth", "authority"),
    ("the_defiant", "The Defiant", "https://thedefiant.io/feed", "eth", "authority"),
    (
        "ethereum_magicians",
        "EIP·Magicians",
        "https://ethereum-magicians.org/latest.rss",
        "eth",
        "official",
    ),
    (
        "ethresearch",
        "ETH Research",
        "https://ethresear.ch/latest.rss",
        "eth",
        "research",
    ),
    (
        "optimism_gov",
        "Optimism·L2",
        "https://gov.optimism.io/latest.rss",
        "eth",
        "official",
    ),
    (
        "cointelegraph_arbitrum",
        "Arbitrum·L2",
        "https://cointelegraph.com/rss/tag/arbitrum",
        "eth",
        "authority",
    ),
    (
        "cointelegraph_optimism",
        "Optimism·快讯",
        "https://cointelegraph.com/rss/tag/optimism",
        "eth",
        "authority",
    ),
)

SOL_FEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "solana",
        "Solana基金会",
        "https://solana.com/news/rss.xml",
        "sol",
        "official",
    ),
    (
        "solana_blog",
        "Solana Blog",
        "https://solana.com/news/rss.xml",
        "sol",
        "official",
    ),
    (
        "solana_status",
        "Solana Status",
        "https://status.solana.com/history.rss",
        "sol",
        "official",
    ),
    (
        "marinade",
        "Marinade",
        "https://marinade.finance/blog/rss.xml",
        "sol",
        "official",
    ),
    (
        "cointelegraph_sol",
        "Cointelegraph·Solana",
        "https://cointelegraph.com/rss/tag/solana",
        "sol",
        "authority",
    ),
    (
        "cointelegraph_fantom",
        "Fantom·生态",
        "https://cointelegraph.com/rss/tag/fantom",
        "sol",
        "authority",
    ),
)

# 美股宏观（财经 RSS）
MACRO_FEED_KEYS: tuple[str, ...] = (
    "fed",
    "bls",
    "reuters",
    "cnbc",
    "marketwatch",
    "benzinga",
)

# 全市场宏观 / 监管（加密权威媒体）
CRYPTO_MACRO_FEEDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "blockworks",
        "Blockworks",
        "https://blockworks.co/feed",
        "macro",
        "authority",
    ),
    (
        "decrypt",
        "Decrypt·监管",
        "https://decrypt.co/feed",
        "macro",
        "authority",
    ),
    (
        "cointelegraph_policy",
        "CT·全球政策",
        "https://cointelegraph.com/rss/tag/regulation",
        "macro",
        "authority",
    ),
)

CRYPTO_MACRO_FEED_KEYS: tuple[str, ...] = tuple(k for k, *_ in CRYPTO_MACRO_FEEDS)

# 与 CoinDesk/The Block 同级的重磅权威源（计分 7~12）
PREMIUM_AUTHORITY_FEED_KEYS: frozenset[str] = frozenset(
    k
    for k, *_ in (
        BTC_FEEDS + ETH_FEEDS + SOL_FEEDS + CRYPTO_MACRO_FEEDS
    )
    if k
    not in (
        "glassnode",
        "ethresearch",
        "solana_status",
        "sec_btc",
    )
)

LANE_FEED_MAP: dict[str, tuple[tuple[str, str, str, str, str], ...]] = {
    "btc": BTC_FEEDS,
    "eth": ETH_FEEDS,
    "sol": SOL_FEEDS,
}


def feed_url(cfg_rss: dict[str, Any], key: str, default: str) -> str:
    return str(cfg_rss.get(key) or default).strip()
