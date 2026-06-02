"""
CryptoPanic 全球加密快讯
API 文档: https://cryptopanic.com/developers/api/
需在 config.api_keys.cryptopanic 填写 auth_token。
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.http_client import fetch_json
from collectors.news_impact import (
    merge_scores,
    score_from_cryptopanic_votes,
    score_from_title,
)
from collectors.types import NewsItem

logger = logging.getLogger(__name__)

API_URL = "https://cryptopanic.com/api/developer/v2/posts/"


def fetch_cryptopanic(
    auth_token: str,
    *,
    timeout: int = 15,
    filter_kind: str = "news",
    public_only: bool = True,
) -> tuple[list[NewsItem], str | None]:
    """
    拉取 CryptoPanic 帖子列表。
    :return: (资讯列表, 错误信息；成功时错误为 None)
    """
    if not auth_token or not str(auth_token).strip():
        return [], "CryptoPanic：未配置 api_keys.cryptopanic，已跳过"

    params: dict[str, Any] = {
        "auth_token": auth_token.strip(),
        "filter": filter_kind,
        "public": "true" if public_only else "false",
    }

    try:
        data = fetch_json(API_URL, params=params, timeout=timeout)
    except Exception as exc:
        logger.warning("CryptoPanic 请求失败: %s", exc)
        return [], f"CryptoPanic：{exc}"

    results = data.get("results") or []
    items: list[NewsItem] = []

    for row in results:
        title = (row.get("title") or "").strip()
        if not title:
            continue

        source_info = row.get("source") or {}
        source_name = source_info.get("title") or source_info.get("domain") or "CryptoPanic"

        url = row.get("url") or row.get("original_url") or ""
        votes = row.get("votes") or {}
        currencies = [c.get("code", "") for c in (row.get("currencies") or []) if c.get("code")]

        title_score, kw, logic = score_from_title(title)
        vote_score = score_from_cryptopanic_votes(votes)
        impact = merge_scores(title_score, vote_score)

        keywords = list(dict.fromkeys(currencies + kw))[:3]
        vote_logic = (
            f"社区投票 利多{votes.get('positive', 0)} / 利空{votes.get('negative', 0)}"
            + (" · 标记重要" if votes.get("important") else "")
        )

        items.append(
            NewsItem(
                title=title,
                source=str(source_name),
                url=url,
                impact_score=impact,
                keywords=keywords,
                logic=f"{logic}；{vote_logic}",
                published_at=str(row.get("published_at") or ""),
                raw=row,
                feed_type="crypto",
            )
        )

    return items, None
