"""
分品种分层 raw 分（60/30/10）+ 90 天品种内百分位归一 → 0~100 展示分。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from collectors.community_sentiment import LaneSentiment
from collectors.funding_collect import FundingSnapshot
from collectors.macro_collect import MacroSnapshot
from collectors.news_recency import filter_recent_news
from collectors.types import NewsItem
from core.config_loader import load_config
from scoring.layered_score import composite_raw_score
from scoring.multi_asset import SYMBOLS
from scoring.percentile_normalize import (
    normalize_and_persist,
    percentile_from_list,
    percentile_rank_score,
)
from storage.symbol_score_db import insert_raw_score
from scoring.utils import clamp
from storage.onchain_db import OnchainSnapshot, get_latest_snapshot

# 4h 槽位：90 天约 540 点
_MAX_HISTORY_POINTS = 90 * 6


def _use_layered_percentile(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get("scoring", {}).get("use_layered_percentile", True))


def price_proxy_authority_score(symbol: str, at: datetime) -> float:
    """无历史资讯存档时，用价格四分项代理权威层 0~100。"""
    from scoring.multi_asset import (
        _funding_snapshot_for_symbol,
        _macro_snapshot_at,
        _pct_at,
        _volatility_proxy,
    )
    from scoring.funding_score import score_funding
    from scoring.macro_score import score_macro
    from scoring.constants import WEIGHT_FUNDAMENTALS, WEIGHT_REGULATION
    from scoring.utils import map_impact_to_points

    btc_4h = _pct_at("BTC", at, 0, 4)
    btc_24h = _pct_at("BTC", at, 0, 24)
    rets_7 = [_pct_at("BTC", at, i * 4, 4) for i in range(7)]
    mom7 = sum(rets_7) / len(rets_7) if rets_7 else btc_24h
    vol7 = _volatility_proxy(rets_7)

    macro_pts, _ = score_macro(_macro_snapshot_at(btc_24h, vol7))
    sym_4h = _pct_at(symbol, at, 0, 4)
    sym_24h = _pct_at(symbol, at, 0, 24)

    reg_impact = (sym_4h - btc_4h) * 2.8 + mom7 * 0.15
    reg_pts = round(map_impact_to_points(reg_impact, WEIGHT_REGULATION), 1)
    fund_pts, _ = score_funding(
        _funding_snapshot_for_symbol(symbol, sym_4h, sym_24h, vol7)
    )
    funda_impact = sym_4h * 1.5 + sym_24h * 0.35
    funda_pts = round(
        map_impact_to_points(funda_impact, WEIGHT_FUNDAMENTALS), 1
    )
    return round(clamp(macro_pts + reg_pts + fund_pts + funda_pts, 0.0, 100.0), 1)


def compute_raw_composite(
    symbol: str,
    *,
    at: datetime | None = None,
    all_news: list[NewsItem] | None = None,
    macro: MacroSnapshot | None = None,
    funding: FundingSnapshot | None = None,
    onchain: OnchainSnapshot | None = None,
    community: dict[str, LaneSentiment] | None = None,
    use_price_proxy: bool = False,
) -> tuple[float, float, float, float]:
    """返回 (raw_news, raw_onchain, raw_community, raw_composite)。"""
    sym = symbol.upper()
    if use_price_proxy or not all_news or at is None:
        if at is None:
            at = datetime.now()
        news = price_proxy_authority_score(sym, at)
        from scoring.historical_onchain import build_onchain_proxy_at
        from scoring.layered_score import score_onchain_layer

        snap = onchain if onchain is not None else build_onchain_proxy_at(at)
        chain = score_onchain_layer(sym, snap)
        comm = 50.0
        total = round(news * 0.60 + chain * 0.30 + comm * 0.10, 2)
        return news, chain, comm, round(clamp(total, 0.0, 100.0), 2)

    if macro is None or funding is None:
        raise ValueError("live raw 计分需要 macro 与 funding")

    return composite_raw_score(
        sym,
        all_news=all_news,
        macro=macro,
        funding=funding,
        onchain=onchain,
        community=community,
    )


def compute_normalized_symbol_scores_at(
    at: datetime,
    *,
    all_news: list[NewsItem] | None = None,
    macro: MacroSnapshot | None = None,
    funding: FundingSnapshot | None = None,
    onchain: OnchainSnapshot | None = None,
    community: dict[str, LaneSentiment] | None = None,
    persist: bool = True,
) -> dict[str, float]:
    """单时刻三品种归一化展示分。"""
    cfg = load_config()
    if not _use_layered_percentile(cfg):
        from scoring.multi_asset import _legacy_price_scores_at

        return _legacy_price_scores_at(at, onchain=onchain)

    use_proxy = not all_news
    snap = onchain if onchain is not None else get_latest_snapshot()
    ts = at.strftime("%Y-%m-%d %H:%M:%S")
    out: dict[str, float] = {}

    for sym in SYMBOLS:
        rn, ro, rc, raw = compute_raw_composite(
            sym,
            at=at,
            all_news=all_news,
            macro=macro,
            funding=funding,
            onchain=snap,
            community=community,
            use_price_proxy=use_proxy,
        )
        if persist:
            norm, _ = normalize_and_persist(
                sym, ts, rn, ro, rc, raw
            )
        else:
            norm = percentile_rank_score(sym, raw, exclude_current_time=ts)
        out[sym] = norm
    return out


def compute_live_normalized_scores(
    *,
    all_news: list[NewsItem],
    macro: MacroSnapshot,
    funding: FundingSnapshot,
    onchain_snap: OnchainSnapshot | None,
    community_lanes: dict[str, LaneSentiment] | None,
    fetch_time: datetime,
) -> dict[str, float]:
    """实时拉取：权威资讯 + 链上 + 社区分层后百分位归一。"""
    cfg = load_config()
    all_news = filter_recent_news(all_news, cfg=cfg)
    return compute_normalized_symbol_scores_at(
        fetch_time,
        all_news=all_news,
        macro=macro,
        funding=funding,
        onchain=onchain_snap,
        community=community_lanes,
        persist=True,
    )


def compute_normalized_scores_chronological(
    slots: list[datetime],
    *,
    persist: bool = True,
) -> dict[str, dict[str, float]]:
    """
    按时间顺序批量计分（回测/补历史）。
    返回 { "2025-01-01 00:00:00": {"BTC": .., "ETH": .., "SOL": ..}, ... }
    """
    raw_hist: dict[str, list[float]] = defaultdict(list)
    result: dict[str, dict[str, float]] = {}

    for at in slots:
        ts = at.strftime("%Y-%m-%d %H:%M:%S")
        sym_scores: dict[str, float] = {}
        for sym in SYMBOLS:
            rn, ro, rc, raw = compute_raw_composite(
                sym, at=at, use_price_proxy=True
            )
            hist = raw_hist[sym]
            norm = percentile_from_list(hist, raw)
            sym_scores[sym] = norm
            hist.append(raw)
            # 仅保留近 90 天窗口（按 4h 槽位数）
            if len(hist) > _MAX_HISTORY_POINTS:
                raw_hist[sym] = hist[-_MAX_HISTORY_POINTS:]
            if persist:
                insert_raw_score(
                    ts,
                    sym,
                    raw_news=rn,
                    raw_onchain=ro,
                    raw_community=rc,
                    raw_composite=raw,
                    norm_score=norm,
                )
        result[ts] = sym_scores

    return result
