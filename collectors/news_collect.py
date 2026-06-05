"""
资讯采集汇总
四车道（BTC/ETH/SOL/宏观）隔离 → 质量筛选 → 分级计分 → 合并供晴雨表。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.news_cryptopanic import fetch_cryptopanic_lane
from collectors.news_macro_rss import fetch_crypto_macro_feeds, fetch_macro_feeds
from collectors.news_pipeline import merge_lane_batches, process_lane_batch
from collectors.news_source_catalog import (
    BTC_FEEDS,
    CRYPTO_MACRO_FEEDS,
    ETH_FEEDS,
    LANE_FEED_MAP,
    MACRO_FEED_KEYS,
    SOL_FEEDS,
    feed_url,
)
from collectors.news_recency import filter_recent_news, sort_by_recency_impact
from collectors.news_rss import fetch_rss_lane_feed
from collectors.types import NewsItem

logger = logging.getLogger(__name__)


def select_top_news(
    items: list[NewsItem],
    limit: int = 10,
    *,
    to_display=None,
) -> list[dict[str, Any]]:
    convert = to_display or (lambda n: n.to_display_dict())
    recent = filter_recent_news(items)
    sorted_items = sort_by_recency_impact(recent)
    return [convert(n) for n in sorted_items[:limit]]


def _fetch_lane_rss(
    lane: str,
    feeds: tuple,
    rss_cfg: dict[str, Any],
    *,
    timeout: int,
    max_rss: int,
    ds: dict[str, Any],
) -> tuple[list[NewsItem], list[str], list[str]]:
    items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    for key, name, default_url, asset_lane, tier in feeds:
        cfg_key = key
        if ds.get(cfg_key) is False:
            continue
        url = feed_url(rss_cfg, cfg_key, default_url)
        batch, err = fetch_rss_lane_feed(
            cfg_key,
            name,
            url,
            asset_lane=asset_lane,
            source_tier=tier,
            timeout=timeout,
            max_items=max_rss,
        )
        if err:
            errors.append(err)
            summary.append(f"{name}：失败")
        elif batch:
            items.extend(batch)
            summary.append(f"{name}：{len(batch)} 条")

    processed = process_lane_batch(items, lane)
    return processed, summary, errors


def collect_btc_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("news", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_max_items", 30))
    rss_urls = collector_cfg.get("rss", {}) or {}

    items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    if ds.get("cryptopanic", False):
        cp, err = fetch_cryptopanic_lane(
            cfg.get("api_keys", {}).get("cryptopanic", ""),
            lane="btc",
            timeout=timeout,
        )
        if err and "未配置" not in err:
            errors.append(err)
        elif cp:
            items.extend(cp)
            summary.append(f"CryptoPanic·BTC：{len(cp)} 条")
        elif err:
            summary.append(err)

    rss_items, s2, e2 = _fetch_lane_rss(
        "btc", BTC_FEEDS, rss_urls, timeout=timeout, max_rss=max_rss, ds=ds
    )
    items.extend(rss_items)
    summary.extend(s2)
    errors.extend(e2)

    return process_lane_batch(items, "btc"), summary, errors


def collect_eth_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("news", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_max_items", 30))
    rss_urls = collector_cfg.get("rss", {}) or {}

    items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    if ds.get("cryptopanic", False):
        cp, err = fetch_cryptopanic_lane(
            cfg.get("api_keys", {}).get("cryptopanic", ""),
            lane="eth",
            timeout=timeout,
        )
        if err and "未配置" not in err:
            errors.append(err)
        elif cp:
            items.extend(cp)
            summary.append(f"CryptoPanic·ETH：{len(cp)} 条")

    rss_items, s2, e2 = _fetch_lane_rss(
        "eth", ETH_FEEDS, rss_urls, timeout=timeout, max_rss=max_rss, ds=ds
    )
    items.extend(rss_items)
    summary.extend(s2)
    errors.extend(e2)

    return process_lane_batch(items, "eth"), summary, errors


def collect_sol_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("news", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_max_items", 30))
    rss_urls = collector_cfg.get("rss", {}) or {}

    items: list[NewsItem] = []
    summary: list[str] = []
    errors: list[str] = []

    if ds.get("cryptopanic", False):
        cp, err = fetch_cryptopanic_lane(
            cfg.get("api_keys", {}).get("cryptopanic", ""),
            lane="sol",
            timeout=timeout,
        )
        if err and "未配置" not in err:
            errors.append(err)
        elif cp:
            items.extend(cp)
            summary.append(f"CryptoPanic·SOL：{len(cp)} 条")

    rss_items, s2, e2 = _fetch_lane_rss(
        "sol", SOL_FEEDS, rss_urls, timeout=timeout, max_rss=max_rss, ds=ds
    )
    items.extend(rss_items)
    summary.extend(s2)
    errors.extend(e2)

    return process_lane_batch(items, "sol"), summary, errors


def collect_crypto_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    """加密三车道合并（计分全量池）。"""
    btc, s1, e1 = collect_btc_news(cfg)
    eth, s2, e2 = collect_eth_news(cfg)
    sol, s3, e3 = collect_sol_news(cfg)
    merged = merge_lane_batches(btc, eth, sol)
    summary = []
    if s1:
        summary.append("BTC[" + "；".join(s1) + "]")
    if s2:
        summary.append("ETH[" + "；".join(s2) + "]")
    if s3:
        summary.append("SOL[" + "；".join(s3) + "]")
    return merged, summary, e1 + e2 + e3


def collect_macro_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    ds = cfg.get("data_sources", {}).get("news", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_macro_max_items", 20))
    rss_macro = dict(collector_cfg.get("rss_macro", {}))
    enabled = ds.get("macro", True)

    if not enabled:
        return [], ["美股宏观 RSS：已关闭"], []

    filtered_macro = {k: rss_macro[k] for k in MACRO_FEED_KEYS if k in rss_macro}
    items, summary, errors = fetch_macro_feeds(
        filtered_macro,
        timeout=timeout,
        max_items=max_rss,
        enabled=True,
    )
    crypto_macro_urls = {
        k: rss_macro[k] for k, *_ in CRYPTO_MACRO_FEEDS if k in rss_macro
    }
    cm_items, cm_sum, cm_err = fetch_crypto_macro_feeds(
        crypto_macro_urls if crypto_macro_urls else dict(rss_macro),
        timeout=timeout,
        max_items=max_rss,
    )
    items.extend(cm_items)
    summary.extend(cm_sum)
    errors.extend(cm_err)
    processed = process_lane_batch(items, "macro")
    return processed, summary, errors


def collect_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    crypto, s1, e1 = collect_crypto_news(cfg)
    macro, s2, e2 = collect_macro_news(cfg)
    summary = []
    if s1:
        summary.append("加密" + "".join(s1))
    if s2:
        summary.append("宏观[" + "；".join(s2) + "]")
    return crypto + macro, summary, e1 + e2


def collect_news_split(
    cfg: dict[str, Any],
) -> tuple[list[NewsItem], list[NewsItem], list[str], list[str]]:
    btc, _, e1 = collect_btc_news(cfg)
    eth, _, e2 = collect_eth_news(cfg)
    sol, _, e3 = collect_sol_news(cfg)
    macro, s2, e2m = collect_macro_news(cfg)

    crypto_merged = merge_lane_batches(btc, eth, sol)
    summary = [
        f"车道 BTC {len(btc)} · ETH {len(eth)} · SOL {len(sol)}",
        "宏观[" + "；".join(s2) + "]" if s2 else "宏观[]",
    ]
    return crypto_merged, macro, summary, e1 + e2 + e3 + e2m
