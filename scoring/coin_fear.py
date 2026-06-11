"""
双指标恐慌计分：
- 大盘恐慌（alternative.me）：三币统一加减
- 币种情绪（CFGI）：仅当前品种加减
"""

from __future__ import annotations

from datetime import datetime

from scoring.utils import clamp

# 分档（UI 与计分共用）
def classify_fear(value: int | None) -> tuple[str, str]:
    if value is None:
        return "fg-unknown", "—"
    v = int(clamp(value, 0, 100))
    if v <= 24:
        return "fg-extreme-fear", "极度恐慌"
    if v <= 49:
        return "fg-fear", "恐慌"
    if v == 50:
        return "fg-neutral", "中性"
    if v <= 74:
        return "fg-greed", "贪婪"
    return "fg-extreme-greed", "极度贪婪"


# 兼容旧名
classify_coin_fear = classify_fear


def coin_fear_score_delta(value: int | None) -> float:
    """单币种 CFGI 情绪 → 仅该品种（权重低于大盘，避免抵消系统性恐慌）。"""
    if value is None:
        return 0.0
    v = int(value)
    if v <= 24:
        return 5.0
    if v <= 49:
        return 2.0
    if v == 50:
        return 0.0
    if v <= 74:
        return -2.0
    return -5.0


def market_fear_score_delta(value: int | None) -> float:
    """大盘 alternative.me → 三币统一（系统性行情权重更高）。"""
    if value is None:
        return 0.0
    v = int(value)
    if v <= 24:
        return 9.0
    if v <= 49:
        return 4.0
    if v == 50:
        return 0.0
    if v <= 74:
        return -4.0
    return -9.0


def apply_fear_adjustments_to_score(
    symbol: str,
    score: float,
    at: datetime | None = None,
) -> tuple[float, dict]:
    """
    百分位归一分 + 币种情绪 + 大盘恐慌 → 最终展示/回测分。
    """
    from storage.coin_fear_db import get_coin_fear_for_slot
    from storage.market_fear_db import get_market_fear_for_slot

    ts = at or datetime.now()
    coin_meta = get_coin_fear_for_slot(symbol, ts)
    market_meta = get_market_fear_for_slot(ts)

    coin_delta = coin_fear_score_delta(coin_meta.get("value"))
    market_delta = market_fear_score_delta(market_meta.get("value"))
    total_delta = coin_delta + market_delta

    out = round(clamp(float(score) + total_delta, 0.0, 100.0), 1)
    zone, label = classify_fear(coin_meta.get("value"))

    return out, {
        "coin": {
            "value": coin_meta.get("value"),
            "label": label,
            "zone": zone,
            "delta": coin_delta,
            "trade_date": coin_meta.get("trade_date"),
            "source": coin_meta.get("source"),
        },
        "market": {
            "value": market_meta.get("value"),
            "delta": market_delta,
            "trade_date": market_meta.get("trade_date"),
            "source": market_meta.get("source", "alternative.me"),
        },
        "delta_total": total_delta,
    }


def apply_coin_fear_to_score(
    symbol: str,
    score: float,
    at: datetime | None = None,
) -> tuple[float, dict]:
    """兼容旧调用：等价于 apply_fear_adjustments_to_score。"""
    out, meta = apply_fear_adjustments_to_score(symbol, score, at)
    coin = meta.get("coin", {})
    return out, {
        "value": coin.get("value"),
        "label": coin.get("label"),
        "zone": coin.get("zone"),
        "delta": meta.get("delta_total"),
        "trade_date": coin.get("trade_date"),
        "source": coin.get("source"),
    }
