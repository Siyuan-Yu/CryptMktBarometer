"""
恐惧贪婪指数（Alternative.me）· 供价格区实时展示，独立短缓存。
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

from collectors.onchain_apis import fetch_fear_greed

logger = logging.getLogger(__name__)

_cache_lock = Lock()
_cache: dict[str, Any] = {"data": None, "updated_at": 0.0}


def classify_fear_greed(value: int | None) -> tuple[str, str]:
    """
    按数值返回 (zone_css, 中文状态)。
    0~24 极度恐惧 | 25~49 恐惧 | 50 中性 | 51~74 贪婪 | 75~100 极度贪婪
    """
    if value is None:
        return "fg-unknown", "—"
    v = int(value)
    if v <= 24:
        return "fg-extreme-fear", "极度恐惧"
    if v <= 49:
        return "fg-fear", "恐惧"
    if v == 50:
        return "fg-neutral", "中性"
    if v <= 74:
        return "fg-greed", "贪婪"
    return "fg-extreme-greed", "极度贪婪"


def fetch_fear_greed_live(*, timeout: int = 10) -> dict[str, Any]:
    """拉取最新恐慌贪婪指数。"""
    val, label_en, err = fetch_fear_greed(timeout=timeout)
    zone, label_zh = classify_fear_greed(val)
    return {
        "value": val,
        "label": label_zh,
        "label_en": label_en or "",
        "zone": zone,
        "source": "alternative.me",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error": err,
    }


def get_cached_fear_greed(
    *,
    cache_seconds: float = 60.0,
    timeout: int = 10,
) -> dict[str, Any]:
    """带短缓存（默认 60 秒，指数日更为主）。"""
    now = time.time()
    with _cache_lock:
        if (
            _cache.get("data")
            and now - float(_cache.get("updated_at") or 0) < cache_seconds
        ):
            return _cache["data"]

    data = fetch_fear_greed_live(timeout=timeout)
    with _cache_lock:
        _cache["data"] = data
        _cache["updated_at"] = now
    return data
