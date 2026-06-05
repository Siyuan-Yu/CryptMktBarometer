"""
品种内部百分位归一化：近 90 天历史 raw_composite → 0~100 展示分。
阈值统一：>55 多、<45 空（由 multi_asset.signal_from_score）。
"""

from __future__ import annotations

from core.config_loader import load_config
from scoring.utils import clamp
from storage.symbol_score_db import get_raw_history, insert_raw_score

_DEFAULT_DAYS = 90
_MIN_SAMPLES = 15


def get_history_days(cfg: dict | None = None) -> int:
    cfg = cfg or load_config()
    return int(cfg.get("scoring", {}).get("percentile_history_days", _DEFAULT_DAYS))


def percentile_rank_score(
    symbol: str,
    raw_value: float,
    *,
    history_days: int | None = None,
    exclude_current_time: str | None = None,
) -> float:
    """
    品种内部百分位：当前 raw 在近 N 天历史中的排位 → 0~100。
    历史最高 raw → 接近 100；历史最低 → 接近 0。
    """
    days = history_days if history_days is not None else get_history_days()
    hist = get_raw_history(
        symbol, days=days, before_time=exclude_current_time
    )
    if len(hist) < _MIN_SAMPLES:
        return round(clamp(raw_value, 0.0, 100.0), 1)

    count_le = sum(1 for h in hist if h <= raw_value)
    pct = count_le / len(hist) * 100.0
    return round(clamp(pct, 0.0, 100.0), 1)


def percentile_from_list(
    history: list[float],
    raw_value: float,
    *,
    min_samples: int = _MIN_SAMPLES,
) -> float:
    """内存历史序列百分位（回测按时间顺序累积）。"""
    if len(history) < min_samples:
        return round(clamp(raw_value, 0.0, 100.0), 1)
    count_le = sum(1 for h in history if h <= raw_value)
    pct = count_le / len(history) * 100.0
    return round(clamp(pct, 0.0, 100.0), 1)


def normalize_and_persist(
    symbol: str,
    fetch_time: str,
    raw_news: float,
    raw_onchain: float,
    raw_community: float,
    raw_composite: float,
) -> tuple[float, float]:
    """归一化并写入历史表。返回 (norm_score, raw_composite)。"""
    norm = percentile_rank_score(
        symbol,
        raw_composite,
        exclude_current_time=fetch_time,
    )
    insert_raw_score(
        fetch_time,
        symbol,
        raw_news=raw_news,
        raw_onchain=raw_onchain,
        raw_community=raw_community,
        raw_composite=raw_composite,
        norm_score=norm,
    )
    return norm, raw_composite
