"""
多品种统一计分（BTC / ETH / SOL）

- 同一套权重（30/30/35/5）与同一公式：四分项之和 = 0~100
- 各品种仅价格输入不同，避免 ETH/SOL 被错误加权压到 20 分以下
- 信号由分数唯一推导：≥55 多 | ≤45 空 | 其余 中性
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from scoring.constants import (
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)
from scoring.funding_score import score_funding
from scoring.macro_score import score_macro
from scoring.utils import clamp, map_impact_to_points
from storage import price_db
from storage.onchain_db import OnchainSnapshot

SYMBOLS = ("BTC", "ETH", "SOL")

SIGNAL_LONG_THRESHOLD = 55.0
SIGNAL_SHORT_THRESHOLD = 45.0


def signal_from_score(score: float) -> str:
    """信号与分数 100% 对应。"""
    if score >= SIGNAL_LONG_THRESHOLD:
        return "多"
    if score <= SIGNAL_SHORT_THRESHOLD:
        return "空"
    return "中性"


def score_status_label(score: float) -> str:
    """导出用中文状态（与 signal_from_score 阈值一致）。"""
    if score >= SIGNAL_LONG_THRESHOLD:
        return "看多"
    if score <= SIGNAL_SHORT_THRESHOLD:
        return "看空"
    return "中性"


def _pct_at(symbol: str, at: datetime, hours_back: int, span: int) -> float:
    t_end = at - timedelta(hours=hours_back)
    t_start = t_end - timedelta(hours=span)
    p0 = price_db.get_close_at(symbol, t_start)
    p1 = price_db.get_close_at(symbol, t_end)
    if p0 is None or p1 is None or p0 == 0:
        return 0.0
    return (p1 - p0) / p0 * 100.0


def _volatility_proxy(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(abs(v) for v in values) / len(values)


def _macro_snapshot_at(btc_24h: float, vol7: float) -> MacroSnapshot:
    treasury_chg_bps = round(btc_24h * 6.0, 1)
    if btc_24h <= -2.5:
        fed_txt = "市场预期降息，收益率曲线偏鸽"
    elif btc_24h >= 2.5:
        fed_txt = "紧缩预期升温，偏鹰派言论增多"
    else:
        fed_txt = "政策预期平稳，利率路径中性"

    return MacroSnapshot(
        treasury_10y=4.2 + btc_24h * 0.05,
        treasury_10y_chg_bps=treasury_chg_bps,
        fed_expectation=fed_txt,
        calendar_hints=[f"宏观窗口{i}" for i in range(min(6, int(vol7)))],
        summary_lines=[
            f"10Y美债(代理) {4.2 + btc_24h * 0.05:.2f}%",
            f"10Y较前日 {treasury_chg_bps:+.0f}bp",
            f"政策预期：{fed_txt[:40]}",
        ],
    )


def _funding_snapshot_for_symbol(
    symbol: str, sym_4h: float, sym_24h: float, vol7: float
) -> FundingSnapshot:
    liq_line = "爆仓数据偏高，短线波动风险" if vol7 >= 3.5 else "爆仓处于常态区间"
    oi_line = (
        "合约持仓上升，杠杆活跃度升"
        if sym_4h > 0.5
        else "合约持仓下降"
        if sym_4h < -0.5
        else "合约持仓持平"
    )
    return FundingSnapshot(
        summary_lines=[
            f"{symbol} 24h {sym_24h:+.2f}%",
            f"全球市值24h {sym_24h:+.2f}%",
            liq_line,
            oi_line,
        ],
    )


def _legacy_price_scores_at(
    at: datetime,
    *,
    onchain: OnchainSnapshot | None = None,
) -> dict[str, float]:
    """关闭分层百分位时的旧逻辑（价格四分项 + 链上/社区叠加）。"""
    from scoring.community_score import apply_community_to_scores
    from scoring.onchain_objective import apply_symbol_adjustments
    from storage.onchain_db import get_latest_snapshot

    btc_4h = _pct_at("BTC", at, 0, 4)
    btc_24h = _pct_at("BTC", at, 0, 24)
    rets_7 = [_pct_at("BTC", at, i * 4, 4) for i in range(7)]
    mom7 = sum(rets_7) / len(rets_7) if rets_7 else btc_24h
    vol7 = _volatility_proxy(rets_7)

    macro_pts, _ = score_macro(_macro_snapshot_at(btc_24h, vol7))

    out: dict[str, float] = {}
    for symbol in SYMBOLS:
        sym_4h = _pct_at(symbol, at, 0, 4)
        sym_24h = _pct_at(symbol, at, 0, 24)

        reg_impact = (sym_4h - btc_4h) * 2.8 + mom7 * 0.15
        reg_pts = round(map_impact_to_points(reg_impact, WEIGHT_REGULATION), 1)

        fund_pts, _ = score_funding(
            _funding_snapshot_for_symbol(symbol, sym_4h, sym_24h, vol7)
        )

        funda_impact = sym_4h * 1.5 + sym_24h * 0.35
        funda_pts = round(map_impact_to_points(funda_impact, WEIGHT_FUNDAMENTALS), 1)

        total = round(macro_pts + reg_pts + fund_pts + funda_pts, 1)
        out[symbol] = round(clamp(total, 0.0, 100.0), 1)

    snap = onchain if onchain is not None else get_latest_snapshot()
    out = apply_symbol_adjustments(out, snap)
    return apply_community_to_scores(out)


def compute_symbol_scores_at(
    at: datetime,
    *,
    onchain: OnchainSnapshot | None = None,
) -> dict[str, float]:
    """
    在时刻 at 为 BTC/ETH/SOL 分别计算 0~100 展示分。
    默认：60% 权威资讯 + 30% 链上 + 10% 社区 → raw，再经 90 天品种内百分位归一。
    """
    from scoring.symbol_scores import compute_normalized_symbol_scores_at

    return compute_normalized_symbol_scores_at(
        at,
        onchain=onchain,
        persist=False,
    )


def compute_btc_category_row(at: datetime) -> dict[str, float | str]:
    """生成 score_history.csv 单条记录（四分项以 BTC 为基准）。"""
    from scoring.symbol_scores import compute_normalized_symbol_scores_at

    scores = compute_normalized_symbol_scores_at(at, persist=False)
    btc_total = scores["BTC"]

    btc_24h = _pct_at("BTC", at, 0, 24)
    rets_7 = [_pct_at("BTC", at, i * 4, 4) for i in range(7)]
    vol7 = _volatility_proxy(rets_7)
    macro_pts, _ = score_macro(_macro_snapshot_at(btc_24h, vol7))

    btc_4h = _pct_at("BTC", at, 0, 4)
    mom7 = sum(rets_7) / len(rets_7) if rets_7 else btc_24h
    reg_impact = mom7 * 0.15
    reg_pts = round(map_impact_to_points(reg_impact, WEIGHT_REGULATION), 1)

    fund_pts, _ = score_funding(
        _funding_snapshot_for_symbol("BTC", btc_4h, btc_24h, vol7)
    )
    funda_impact = btc_4h * 1.5 + btc_24h * 0.35
    funda_pts = round(map_impact_to_points(funda_impact, WEIGHT_FUNDAMENTALS), 1)

    from core.market_rating import rating_from_total_score

    return {
        "fetch_time": at.strftime("%Y-%m-%d %H:%M:%S"),
        "total_score": btc_total,
        "rating": rating_from_total_score(btc_total),
        "macro": macro_pts,
        "regulation": reg_pts,
        "funding": fund_pts,
        "fundamentals": funda_pts,
    }


def compute_us_score_from_row(row: dict[str, str]) -> float | None:
    """美股大盘视角：宏观权重更高，仍映射到 0~100。"""
    macro = _parse_float(row.get("macro"))
    reg = _parse_float(row.get("regulation"))
    fund = _parse_float(row.get("funding"))
    funda = _parse_float(row.get("fundamentals"))
    if macro is None:
        return None

    def _norm(score: float | None, cap: float, weight: float) -> float:
        if score is None or cap <= 0:
            return 0.0
        return (score / cap) * weight

    total = (
        _norm(macro, WEIGHT_MACRO, 50.0)
        + _norm(reg, WEIGHT_REGULATION, 25.0)
        + _norm(fund, WEIGHT_FUNDING, 18.0)
        + _norm(funda, WEIGHT_FUNDAMENTALS, 7.0)
    )
    return round(clamp(total, 0.0, 100.0), 1)


def _parse_float(val: str | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def score_from_history_row(row: dict[str, str], asset: str) -> float | None:
    """
    从 CSV 行读取品种分数。
    BTC 用 total_score；ETH/SOL 必须按时间戳重算（不可对分项做二次加权）。
    """
    asset = asset.lower()
    if asset == "btc":
        t = _parse_float(row.get("total_score"))
        if t is not None:
            return round(clamp(t, 0.0, 100.0), 1)
        parts = [
            _parse_float(row.get("macro")),
            _parse_float(row.get("regulation")),
            _parse_float(row.get("funding")),
            _parse_float(row.get("fundamentals")),
        ]
        if all(p is not None for p in parts):
            return round(clamp(sum(parts), 0.0, 100.0), 1)
        return None

    if asset == "us":
        return compute_us_score_from_row(row)

    if asset in ("eth", "sol"):
        ts = (row.get("fetch_time") or "").strip()
        if not ts:
            return None
        dt = _parse_fetch_time(ts)
        if not dt:
            return None
        sym = asset.upper()
        try:
            scores = compute_symbol_scores_at(dt)
            return scores.get(sym)
        except Exception:
            return None

    return None


def _parse_fetch_time(ts: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ts.strip(), fmt)
        except ValueError:
            continue
    return None
