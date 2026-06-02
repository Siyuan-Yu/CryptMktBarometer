"""
历史资讯批量抓取（2025-01-01 至今）
优先 CryptoPanic 分页 API；辅以 RSS 近期条目。结果写入 impact 库与 news_snapshot.csv（追加）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests

from collectors.news_cryptopanic import fetch_cryptopanic
from collectors.news_impact import score_from_title
from collectors.news_rss import fetch_rss_by_key
from storage import impact_db, news_archive

logger = logging.getLogger(__name__)

CRYPTOPANIC_API = "https://cryptopanic.com/api/developer/v2/posts/"


def _parse_pub(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


def fetch_cryptopanic_historical(
    auth_token: str,
    since: datetime,
    *,
    timeout: int = 20,
    max_pages: int = 200,
) -> list[dict[str, Any]]:
    """分页拉取 CryptoPanic 直至早于 since。"""
    if not auth_token.strip():
        return []

    items: list[dict[str, Any]] = []
    url: str | None = CRYPTOPANIC_API
    params: dict[str, Any] | None = {
        "auth_token": auth_token.strip(),
        "public": "true",
        "filter": "news",
    }
    pages = 0

    while url and pages < max_pages:
        try:
            if params:
                resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "CryptMktBarometer/1.0"})
            else:
                resp = requests.get(url, timeout=timeout, headers={"User-Agent": "CryptMktBarometer/1.0"})
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("CryptoPanic 历史分页失败: %s", exc)
            break

        results = data.get("results") or []
        if not results:
            break

        stop = False
        for row in results:
            pub = _parse_pub(str(row.get("published_at") or ""))
            if pub < since:
                stop = True
                continue
            title = (row.get("title") or "").strip()
            if not title:
                continue
            src = (row.get("source") or {}).get("title") or "CryptoPanic"
            link = row.get("url") or row.get("original_url") or ""
            impact, kw, _ = score_from_title(title)
            items.append(
                {
                    "title": title,
                    "source": src,
                    "url": link,
                    "impact_score": impact,
                    "keywords": kw,
                    "published_at": pub,
                    "use_published_as_fetch": True,
                }
            )

        pages += 1
        next_url = data.get("next")
        if stop or not next_url:
            break
        url = next_url
        params = None
        time.sleep(0.35)

    logger.info("CryptoPanic 历史共 %d 条（%d 页）", len(items), pages)
    return items


def _fetch_cryptopanic_rss(since: datetime) -> list[dict[str, Any]]:
    """无 API Key 时拉取 CryptoPanic 公开 RSS（条数有限）。"""
    try:
        parsed = feedparser.parse(
            "https://cryptopanic.com/news/rss/",
            agent="CryptMktBarometer/1.0",
        )
    except Exception as exc:
        logger.warning("CryptoPanic RSS: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for entry in parsed.entries or []:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        pub = datetime.now(timezone.utc)
        if entry.get("published_parsed"):
            import time as _time

            pub = datetime.fromtimestamp(
                _time.mktime(entry.published_parsed), tz=timezone.utc
            )
        if pub < since:
            continue
        impact, kw, _ = score_from_title(title)
        out.append(
            {
                "title": title,
                "source": "CryptoPanic RSS",
                "url": entry.get("link", ""),
                "impact_score": impact,
                "keywords": kw,
                "published_at": pub,
                "use_published_as_fetch": True,
            }
        )
    return out


def import_items_to_db(items: list[dict[str, Any]]) -> int:
    """写入 impact 库待测算表。"""
    import weight_optimizer as wo

    n = 0
    for row in items:
        pub = row.get("published_at")
        if isinstance(pub, str):
            pub = _parse_pub(pub)
        if not isinstance(pub, datetime):
            pub = datetime.now(timezone.utc)
        mod = wo.classify_news_module(row["title"])
        wo_is_event = wo.is_breaking_event(row["title"], mod)
        impact_db.insert_news_pending(
            title=row["title"],
            source=row.get("source", ""),
            url=row.get("url", ""),
            module=mod,
            published_at=pub,
            predicted_impact=float(row.get("impact_score") or 0),
            is_event=wo_is_event,
        )
        n += 1
    return n


def fetch_historical_news(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    拉取 2025-01-01 至今历史资讯，追加 CSV + impact 库。
    不删除、不覆盖已有文件。
    """
    cfg = cfg or {}
    opt = cfg.get("weight_optimizer", {}).get("historical", {})
    start_str = opt.get("start_date", "2025-01-01")
    since = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)

    summary: dict[str, Any] = {"start": start_str, "end": end.date().isoformat(), "sources": {}}
    all_items: list[dict[str, Any]] = []

    token = (cfg.get("api_keys", {}).get("cryptopanic") or "").strip()
    if token and cfg.get("data_sources", {}).get("news", {}).get("cryptopanic", True):
        cp = fetch_cryptopanic_historical(token, since, max_pages=int(opt.get("max_pages", 150)))
        all_items.extend(cp)
        summary["sources"]["cryptopanic"] = len(cp)
    else:
        cp_rss = _fetch_cryptopanic_rss(since)
        all_items.extend(cp_rss)
        summary["sources"]["cryptopanic"] = f"rss_{len(cp_rss)}_no_api_key"

    collector = cfg.get("collector", {})
    rss_urls = collector.get("rss", {})
    ds_news = cfg.get("data_sources", {}).get("news", {})
    for key in ("coindesk", "theblock"):
        if not ds_news.get(key, False):
            continue
        items, err = fetch_rss_by_key(key, rss_urls, max_items=int(opt.get("rss_max_items", 50)))
        if err:
            summary["sources"][key] = f"error:{err[:40]}"
            continue
        rows = []
        for it in items:
            pub = _parse_pub(it.published_at) if it.published_at else datetime.now(timezone.utc)
            if pub >= since:
                rows.append(
                    {
                        "title": it.title,
                        "source": it.source,
                        "url": it.url,
                        "impact_score": it.impact_score,
                        "keywords": it.keywords,
                        "published_at": pub,
                        "use_published_as_fetch": True,
                    }
                )
        all_items.extend(rows)
        summary["sources"][key] = len(rows)

    csv_added = news_archive.append_news_rows(all_items)
    db_added = import_items_to_db(all_items)
    summary["csv_appended"] = csv_added
    summary["db_records"] = db_added
    summary["total_fetched"] = len(all_items)
    return summary
