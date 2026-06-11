"""
无 CFGI API Key 时：由小时 K 线推导各币种独立恐慌代理分（0~100）。
BTC/ETH/SOL 各自波动，互不绑定。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from scoring.multi_asset import _pct_at, _volatility_proxy
from scoring.utils import clamp
from storage import price_db


def proxy_coin_fear_value(symbol: str, at: datetime) -> int:
    sym = symbol.upper()
    sym_24 = _pct_at(sym, at, 0, 24) or 0.0
    sym_4 = _pct_at(sym, at, 0, 4) or 0.0
    btc_24 = _pct_at("BTC", at, 0, 24) or 0.0
    rets = [_pct_at(sym, at, i * 4, 4) for i in range(6)]
    vol = _volatility_proxy(rets)

    rel = sym_24 - btc_24 * 0.35
    if sym == "ETH":
        rel += sym_4 * 0.15
    elif sym == "SOL":
        rel += sym_4 * 0.25 - vol * 0.08

    raw = 50.0 - sym_24 * 3.2 - vol * 1.8 + rel * 1.4 + sym_4 * 0.6
    return int(round(clamp(raw, 0.0, 100.0)))


def proxy_coin_fear_for_date(symbol: str, trade_date: str) -> int:
    """自然日取当日 20:00 槽位代理。"""
    dt = datetime.strptime(trade_date, "%Y-%m-%d").replace(hour=20, minute=0)
    if price_db.get_close_at(symbol, dt) is None:
        dt = datetime.strptime(trade_date, "%Y-%m-%d").replace(hour=12, minute=0)
    return proxy_coin_fear_value(symbol, dt)
