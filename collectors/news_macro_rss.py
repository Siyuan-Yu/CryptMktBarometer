"""
美股 & 宏观专属 RSS 采集
与加密源彻底分离：仅财经/政策/宏观类公开 RSS，不接入 CoinDesk / The Block 等。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.news_impact import score_from_macro_title, score_from_title
from collectors.news_rss import fetch_rss_feed
from collectors.news_source_catalog import CRYPTO_MACRO_FEEDS, MACRO_FEED_KEYS
from collectors.types import NewsItem

logger = logging.getLogger(__name__)

# (配置 key, 展示名, 默认 RSS)
MACRO_FEED_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("fed", "美联储", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("bls", "劳工统计局BLS", "https://www.bls.gov/feed/bls_latest.rss"),
    ("fred_blog", "FRED", "https://fredblog.stlouisfed.org/feed/"),
    ("sec", "SEC", "https://www.sec.gov/news/pressreleases.rss"),
    ("reuters", "Reuters路透", "https://feeds.reuters.com/reuters/businessNews"),
    ("bloomberg", "Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("cnbc", "CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("wsj", "华尔街日报", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("marketwatch", "MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("ft", "金融时报FT", "https://www.ft.com/rss/home"),
    ("benzinga", "Benzinga", "https://www.benzinga.com/news/feed"),
    ("wallstreetcn", "华尔街见闻", "https://rss.wallstreetcn.com/"),
)


def _score_macro_item(title: str) -> tuple[float, list[str], str]:
    return score_from_macro_title(title)


def fetch_macro_feeds(
    feed_urls: dict[str, Any],
    *,
    timeout: int = 15,
    max_items: int = 20,
    enabled: bool = True,
) -> tuple[list[NewsItem], list[str], list[str]]:
    """
    拉取全部已配置的美股/宏观 RSS。
    :return: (资讯列表, 成功摘要, 错误列表)
    """
    if not enabled:
        return [], ["美股宏观 RSS：已关闭"], []

    all_items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    catalog = {k: (n, u) for k, n, u in MACRO_FEED_CATALOG}
    keys = [k for k in MACRO_FEED_KEYS if k in catalog]
    for key in keys:
        name, default_url = catalog[key]
        url = str(feed_urls.get(key) or default_url).strip()
        items, err = fetch_rss_feed(
            name,
            url,
            timeout=timeout,
            max_items=max_items,
            feed_type="macro",
            score_fn=_score_macro_item,
            asset_lane="macro",
            source_tier="authority",
            feed_key=key,
        )
        if err:
            errors.append(err)
            summary.append(f"{name}：失败")
            logger.debug("宏观 RSS %s: %s", name, err)
        elif items:
            all_items.extend(items)
            summary.append(f"{name}：{len(items)} 条")

    logger.info("美股宏观资讯合计 %d 条", len(all_items))
    return all_items, summary, errors


def fetch_crypto_macro_feeds(
    feed_urls: dict[str, Any],
    *,
    timeout: int = 15,
    max_items: int = 20,
) -> tuple[list[NewsItem], list[str], list[str]]:
    """Blockworks / Decrypt 监管 / CT 全球政策等加密宏观源。"""
    all_items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    for key, name, default_url, asset_lane, tier in CRYPTO_MACRO_FEEDS:
        url = str(feed_urls.get(key) or default_url).strip()
        items, err = fetch_rss_feed(
            name,
            url,
            timeout=timeout,
            max_items=max_items,
            feed_type="macro",
            score_fn=_score_macro_item,
            asset_lane=asset_lane,
            source_tier=tier,
            feed_key=key,
        )
        if err:
            errors.append(err)
            summary.append(f"{name}：失败")
        elif items:
            all_items.extend(items)
            summary.append(f"{name}：{len(items)} 条")

    return all_items, summary, errors
