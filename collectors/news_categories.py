"""
资讯分类过滤：BTC / SOL / ETH / 美股宏观 独立 TOP 列表
加密池与宏观池分离；宏观板块剔除加密关键词。
"""

from __future__ import annotations

import re
from typing import Any

from collectors.types import NewsItem

# BTC 生态（现货 ETF、灰度、SEC、矿工、链上、减半、机构持仓）
_BTC_PATTERNS = re.compile(
    r"\b(bitcoin|\bbtc\b|\$btc|satosh|halving|hash rate|hashrate|"
    r"miner|mining|microstrategy|mstr|grayscale|gbtc|ark invest|bitcoin core|"
    r"bitcoin etf|spot btc|"
    r"btc etf|blackrock.*btc|fidelity.*btc|sec.*btc|btc.*sec|"
    r"on-chain|onchain|whale|institutional|treasury.*btc|coinbase.*custody|"
    r"灰度|比特币|减半|矿工|链上|现货etf|机构持仓|etf流入|etf流出)\b",
    re.I,
)

_BTC_BLOCK = re.compile(
    r"\b(solana|\bsol\b|\$sol|ethereum|\beth\b|\$eth|bonk|jito|"
    r"cpi|nonfarm|fomc|powell|treasury yield|s&p 500|nasdaq composite)\b",
    re.I,
)

_BTC_RELAXED = re.compile(
    r"\b(bitcoin|\bbtc\b|\$btc|比特币|btc etf|bitcoin etf)\b",
    re.I,
)

# SOL 生态（公链 / 基金会 / Pay.sh / 链上升级）
_SOL_PATTERNS = re.compile(
    r"\b(solana|\bsol\b|\$sol|jupiter|jito|raydium|marinade|phantom|fantom|ftm|bonk|wif|"
    r"pump\.fun|orca|meteora|tensor|helius|firedancer|saga|"
    r"sol etf|solana etf|solana foundation|validator|pay\.sh|pay sh|"
    r"onchain perps|agave|mainnet upgrade|solana ecosystem)\b",
    re.I,
)

_SOL_BLOCK = re.compile(
    r"\b(bitcoin|\bbtc\b|\$btc|ethereum|\beth\b|\$eth|"
    r"cpi|nonfarm|fomc|powell|treasury yield|s&p 500|nasdaq composite)\b",
    re.I,
)

_SOL_RELAXED = re.compile(
    r"\b(solana|\bsol\b|\$sol|bonk|jito|raydium)\b",
    re.I,
)

# ETH 生态 / SEC / ETF
_ETH_PATTERNS = re.compile(
    r"\b(ethereum|\beth\b|\$eth|ether\b|eip-\d+|eip\d+|erc-20|erc20|"
    r"layer.?2|\bl2\b|arbitrum|optimism|base chain|staking|beacon|"
    r"bankless|defiant|vitalik|gas fee|eth etf|spot eth|consensys|uniswap|"
    r"grayscale eth|blackrock eth|sec.*eth|eth.*sec)\b",
    re.I,
)

_ETH_RELAXED = re.compile(
    r"\b(ethereum|\beth\b|\$eth|staking|eth etf|layer 2)\b",
    re.I,
)

_ETH_BLOCK = re.compile(
    r"\b(solana|\bsol\b|\$sol|bitcoin|\bbtc\b|\$btc|bonk|jito)\b",
    re.I,
)

# 美股 / 宏观（用户指定关键词）
_MACRO_PATTERNS = re.compile(
    r"\b(cpi|ppi|core pce|\bpce\b|nonfarm|nfp|jobs report|unemployment|"
    r"federal reserve|\bfed\b|fomc|powell|rate cut|rate hike|interest rate|"
    r"inflation|treasury yield|10-year|10y yield|bond yield|"
    r"s&p 500|s&p500|nasdaq|dow jones|wall street|stock market|"
    r"gdp|recession|dollar index|\bdxy\b|pmi|earnings|"
    r"国债|非农|美联储|加息|降息|通胀|美股|标普|纳斯达克|道琼斯|"
    r"美债|十年期|财报|纳指|道指|sec\b|证监会)\b",
    re.I,
)

# 宏观板块排除加密
_CRYPTO_BLOCK = re.compile(
    r"\b(bitcoin|\bbtc\b|\$btc|ethereum|\beth\b|\$eth|solana|\bsol\b|\$sol|"
    r"crypto|cryptocurrency|blockchain|defi|nft|digital currency|"
    r"加密|数字货币|比特币|以太坊|solana)\b",
    re.I,
)

_TRUSTED_MACRO_SOURCES = re.compile(
    r"美联储|fed|bls|劳工|fred|sec|reuters|路透|bloomberg|彭博|"
    r"cnbc|wsj|华尔街|marketwatch|benzinga|金融时报|wallstreet",
    re.I,
)


def _item_text(item: NewsItem) -> str:
    parts = [item.title, item.logic, " ".join(item.keywords)]
    raw_title = (item.raw or {}).get("title") or ""
    if raw_title and raw_title not in parts[0]:
        parts.append(raw_title)
    return " ".join(p for p in parts if p).lower()


def _currency_codes(item: NewsItem) -> set[str]:
    codes: set[str] = set()
    for kw in item.keywords:
        if str(kw).upper() in ("BTC", "ETH", "SOL"):
            codes.add(str(kw).upper())
    for c in (item.raw or {}).get("currencies") or []:
        code = (c.get("code") if isinstance(c, dict) else c) or ""
        if code:
            codes.add(str(code).upper())
    return codes


def is_crypto_topic(item: NewsItem) -> bool:
    return bool(_CRYPTO_BLOCK.search(_item_text(item)))


def classify_news_tag(item: NewsItem) -> str:
    """TOP10 四类彩色标签。"""
    if item.feed_type == "macro":
        return "美股宏观"
    src = (item.source or "").lower()
    if "solana" in src or "solana生态" in item.source:
        return "SOL生态"
    if "以太坊" in item.source or "ethereum" in src:
        return "ETH生态"
    btc = is_btc_related(item, relaxed=True)
    sol = is_sol_related(item, relaxed=True)
    eth = is_eth_related(item, relaxed=True)
    if btc and not sol and not eth:
        return "BTC生态"
    if sol and not eth and not btc:
        return "SOL生态"
    if eth and not sol and not btc:
        return "ETH生态"
    if btc:
        return "BTC生态"
    if sol:
        return "SOL生态"
    if eth:
        return "ETH生态"
    return "全市场加密"


def is_btc_related(item: NewsItem, *, relaxed: bool = False) -> bool:
    if item.feed_type == "macro":
        return False
    codes = _currency_codes(item)
    if "ETH" in codes or "SOL" in codes:
        if "BTC" not in codes:
            return False
    if "BTC" in codes and "ETH" not in codes and "SOL" not in codes:
        return True
    text = _item_text(item)
    pat = _BTC_RELAXED if relaxed else _BTC_PATTERNS
    if not pat.search(text):
        return False
    if _BTC_BLOCK.search(text) and not re.search(
        r"\b(bitcoin|\bbtc\b|\$btc|halving|grayscale|gbtc|etf)\b", text, re.I
    ):
        return False
    if is_macro_related(item, allow_crypto_context=True) and not re.search(
        r"\b(bitcoin|\bbtc\b|\$btc)\b", text, re.I
    ):
        return False
    return True


def is_sol_related(item: NewsItem, *, relaxed: bool = False) -> bool:
    if item.feed_type == "macro":
        return False
    codes = _currency_codes(item)
    if "BTC" in codes or "ETH" in codes:
        if "SOL" not in codes:
            return False
    if "SOL" in codes and "ETH" not in codes and "BTC" not in codes:
        return True
    text = _item_text(item)
    pat = _SOL_RELAXED if relaxed else _SOL_PATTERNS
    if not pat.search(text):
        return False
    if _SOL_BLOCK.search(text) and not re.search(
        r"\b(solana|\bsol\b|\$sol|pay\.sh)\b", text, re.I
    ):
        return False
    if is_macro_related(item, allow_crypto_context=True) and not re.search(
        r"\b(solana|\bsol\b|\$sol)\b", text, re.I
    ):
        return False
    return True


def is_eth_related(item: NewsItem, *, relaxed: bool = False) -> bool:
    if item.feed_type == "macro":
        return False
    codes = _currency_codes(item)
    if "BTC" in codes and "ETH" not in codes:
        return False
    if "SOL" in codes and "ETH" not in codes:
        return False
    if "ETH" in codes:
        return True
    text = _item_text(item)
    pat = _ETH_RELAXED if relaxed else _ETH_PATTERNS
    if not pat.search(text):
        return False
    if _ETH_BLOCK.search(text) and not re.search(
        r"\b(ethereum|\beth\b|\$eth|vitalik)\b", text, re.I
    ):
        return False
    if is_macro_related(item, allow_crypto_context=True) and not re.search(
        r"\b(ethereum|\beth\b|\$eth)\b", text, re.I
    ):
        return False
    return True


def is_macro_related(item: NewsItem, *, allow_crypto_context: bool = False) -> bool:
    if item.feed_type == "macro":
        if not allow_crypto_context and is_crypto_topic(item):
            return False
        if _MACRO_PATTERNS.search(_item_text(item)):
            return True
        if _TRUSTED_MACRO_SOURCES.search(item.source):
            return True
        return not is_crypto_topic(item)

    text = _item_text(item)
    if not allow_crypto_context and is_crypto_topic(item):
        return False
    return bool(_MACRO_PATTERNS.search(text))


def filter_by_category(
    items: list[NewsItem],
    category: str,
    *,
    relaxed: bool = False,
) -> list[NewsItem]:
    """category: btc | sol | eth | macro"""
    if category == "btc":
        fn = lambda i: is_btc_related(i, relaxed=relaxed)
    elif category == "sol":
        fn = lambda i: is_sol_related(i, relaxed=relaxed)
    elif category == "eth":
        fn = lambda i: is_eth_related(i, relaxed=relaxed)
    elif category == "macro":
        result: list[NewsItem] = []
        for i in items:
            if is_crypto_topic(i):
                continue
            if i.feed_type == "macro":
                result.append(i)
            elif is_macro_related(i, allow_crypto_context=False):
                result.append(i)
        return result
    else:
        return []
    return [i for i in items if fn(i)]


def _dedupe_news(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        key = (it.title or "").strip().lower()[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def select_category_top(
    items: list[NewsItem],
    category: str,
    *,
    limit: int = 10,
    to_display,
    pool: str | None = None,
) -> list[dict[str, Any]]:
    """
    按影响分绝对值排序，取分类 TOP N。
    pool: crypto | macro | None(全部) — 限制候选池
    """
    if pool == "crypto":
        candidates = [i for i in items if i.feed_type == "crypto"]
    elif pool == "macro":
        candidates = [
            i for i in items if i.feed_type == "macro" and not is_crypto_topic(i)
        ]
    else:
        candidates = list(items)

    from collectors.news_recency import filter_recent_news, sort_by_recency_impact

    candidates = filter_recent_news(candidates)

    if category == "macro" and pool == "macro":
        filtered = list(candidates)
    else:
        filtered = filter_by_category(candidates, category)
    if len(filtered) < min(3, limit):
        filtered = _dedupe_news(
            filtered + filter_by_category(candidates, category, relaxed=True)
        )

    if category == "macro" and len(filtered) < limit:
        macro_only = [i for i in candidates if i.feed_type == "macro" and not is_crypto_topic(i)]
        filtered = _dedupe_news(filtered + macro_only)

    if category in ("btc", "sol", "eth") and len(filtered) < limit:
        code_map = {"btc": "BTC", "sol": "SOL", "eth": "ETH"}
        codes = code_map[category]
        for it in candidates:
            if codes in _currency_codes(it):
                filtered.append(it)
        filtered = _dedupe_news(filtered)

    sorted_items = sort_by_recency_impact(filtered)
    return [to_display(n) for n in sorted_items[:limit]]
