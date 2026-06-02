"""
资讯采集汇总
加密源与美股宏观源彻底拆分；合并后供计分，分类展示各自独立池。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.news_cryptopanic import fetch_cryptopanic
from collectors.news_macro_rss import fetch_macro_feeds
from collectors.news_rss import fetch_rss_by_key
from collectors.types import NewsItem

logger = logging.getLogger(__name__)


def select_top_news(
    items: list[NewsItem],
    limit: int = 10,
    *,
    to_display=None,
) -> list[dict[str, Any]]:
    """按影响分值绝对值降序，取前 N 条。"""
    convert = to_display or (lambda n: n.to_display_dict())
    sorted_items = sorted(items, key=lambda x: abs(x.impact_score), reverse=True)
    return [convert(n) for n in sorted_items[:limit]]


def collect_crypto_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    """仅 CoinDesk / The Block / CryptoPanic / CoinGlass。"""
    ds = cfg.get("data_sources", {}).get("news", {})
    api_keys = cfg.get("api_keys", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_max_items", 30))
    rss_urls = collector_cfg.get("rss", {}) or collector_cfg.get("rss_crypto", {})

    all_items: list[NewsItem] = []
    summary_lines: list[str] = []
    errors: list[str] = []

    if ds.get("cryptopanic", False):
        items, err = fetch_cryptopanic(
            api_keys.get("cryptopanic", ""),
            timeout=timeout,
        )
        if err:
            if "未配置" in err or "已跳过" in err:
                summary_lines.append(err)
            else:
                errors.append(err)
                summary_lines.append("CryptoPanic：失败")
        else:
            all_items.extend(items)
            summary_lines.append(f"CryptoPanic：{len(items)} 条")

    _labels = {
        "coindesk": "CoinDesk",
        "theblock": "The Block",
        "coinglass": "CoinGlass",
        "solana": "Solana生态",
        "ethereum_blog": "以太坊生态",
    }
    for key in ("coindesk", "theblock", "coinglass", "solana", "ethereum_blog"):
        if not ds.get(key, False):
            continue
        items, err = fetch_rss_by_key(
            key,
            rss_urls,
            timeout=timeout,
            max_items=max_rss,
        )
        label = _labels[key]
        if err:
            if key == "coinglass":
                summary_lines.append(f"{label}：RSS 暂不可用（可改用 Solana/ETH 生态源）")
            else:
                errors.append(err)
                summary_lines.append(f"{label}：失败")
        else:
            for it in items:
                if key == "solana" and "SOL" not in [k.upper() for k in it.keywords]:
                    it.keywords = ["SOL"] + list(it.keywords)
                if key == "ethereum_blog" and "ETH" not in [
                    k.upper() for k in it.keywords
                ]:
                    it.keywords = ["ETH"] + list(it.keywords)
            all_items.extend(items)
            summary_lines.append(f"{label}：{len(items)} 条")

    logger.info("加密资讯 %d 条", len(all_items))
    return all_items, summary_lines, errors


def collect_macro_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    """仅美股/宏观财经 RSS，不含任何加密媒体。"""
    ds = cfg.get("data_sources", {}).get("news", {})
    collector_cfg = cfg.get("collector", {})
    timeout = int(collector_cfg.get("request_timeout_sec", 15))
    max_rss = int(collector_cfg.get("rss_macro_max_items", 20))
    rss_macro = collector_cfg.get("rss_macro", {})

    enabled = ds.get("macro", True)
    return fetch_macro_feeds(
        rss_macro,
        timeout=timeout,
        max_items=max_rss,
        enabled=enabled,
    )


def collect_news(cfg: dict[str, Any]) -> tuple[list[NewsItem], list[str], list[str]]:
    """
    拉取加密 + 宏观全部资讯（计分用全量）。
    :return: (全部资讯, 成功摘要行, 错误列表)
    """
    crypto, s1, e1 = collect_crypto_news(cfg)
    macro, s2, e2 = collect_macro_news(cfg)
    summary = []
    if s1:
        summary.append("加密[" + "；".join(s1) + "]")
    if s2:
        summary.append("宏观[" + "；".join(s2) + "]")
    return crypto + macro, summary, e1 + e2


def collect_news_split(
    cfg: dict[str, Any],
) -> tuple[list[NewsItem], list[NewsItem], list[str], list[str]]:
    """分别返回加密池、宏观池及摘要/错误。"""
    crypto, s1, e1 = collect_crypto_news(cfg)
    macro, s2, e2 = collect_macro_news(cfg)
    summary = []
    if s1:
        summary.append("加密[" + "；".join(s1) + "]")
    if s2:
        summary.append("宏观[" + "；".join(s2) + "]")
    return crypto, macro, summary, e1 + e2
