"""
单币种恐慌 · 多源提供商抽象层。

当前主源：CFGI（稳定落地）
预留校验源：
  - Gate  ETH 独立恐慌 API
  - OKX   SOL 独立恐慌 API

接入新源时仅需实现 BaseCoinFearProvider 子类并注册到 PROVIDERS。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from collectors.cfgi_api import fetch_cfgi_history, fetch_cfgi_latest
from collectors.coin_fear_proxy import proxy_coin_fear_for_date
from core.config_loader import load_config
from storage.coin_fear_db import get_latest_before

logger = logging.getLogger(__name__)

SYMBOLS = ("BTC", "ETH", "SOL")


@dataclass
class FearSample:
    """单源恐慌采样。"""

    value: int
    source: str
    trade_date: str | None = None
    raw: dict[str, Any] | None = None


def _coin_fear_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    return cfg.get("data_sources", {}).get("coin_fear", {})


def _multi_source_enabled(cfg: dict | None = None) -> bool:
    return bool(_coin_fear_cfg(cfg).get("multi_source_check", True))


def _max_deviation(cfg: dict | None = None) -> int:
    return int(_coin_fear_cfg(cfg).get("max_deviation", 12))


class BaseCoinFearProvider(ABC):
    """提供商基类；子类实现 fetch_latest / fetch_history。"""

    name: str = "base"
    supported_symbols: tuple[str, ...] = ()

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in self.supported_symbols

    @abstractmethod
    def fetch_latest(
        self,
        symbol: str,
        trade_date: str,
        *,
        cfg: dict | None = None,
    ) -> FearSample | None:
        ...

    @abstractmethod
    def fetch_history(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
        cfg: dict | None = None,
    ) -> list[FearSample]:
        ...


class CfgiProvider(BaseCoinFearProvider):
    """主数据源：CFGI.io（BTC / ETH / SOL）。"""

    name = "cfgi"
    supported_symbols = SYMBOLS

    def fetch_latest(
        self,
        symbol: str,
        trade_date: str,
        *,
        cfg: dict | None = None,
    ) -> FearSample | None:
        val, err = fetch_cfgi_latest(symbol, cfg=cfg)
        if val is None:
            if err:
                logger.debug("CFGI latest %s: %s", symbol, err)
            return None
        return FearSample(int(val), self.name, trade_date)

    def fetch_history(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
        cfg: dict | None = None,
    ) -> list[FearSample]:
        rows, err = fetch_cfgi_history(
            symbol, start_date=start_date, end_date=end_date, cfg=cfg
        )
        if err:
            logger.debug("CFGI history %s: %s", symbol, err)
        return [
            FearSample(int(r["value"]), self.name, r["trade_date"])
            for r in rows
            if r.get("value") is not None and r.get("trade_date")
        ]


class GateEthFearProvider(BaseCoinFearProvider):
    """
    预留：Gate.io ETH 单币种独立恐慌 API。
    实现 fetch_latest / fetch_history 后自动参与 ETH 多源校验。
    """

    name = "gate"
    supported_symbols = ("ETH",)

    def _enabled(self, cfg: dict | None = None) -> bool:
        cfg = cfg or load_config()
        ds = cfg.get("data_sources", {}).get("gate_fear", {})
        return bool(ds.get("enabled", False))

    def fetch_latest(
        self,
        symbol: str,
        trade_date: str,
        *,
        cfg: dict | None = None,
    ) -> FearSample | None:
        if not self._enabled(cfg):
            return None
        # TODO: 接入 Gate ETH 恐慌端点后在此解析 JSON → FearSample
        # from collectors.coin_fear_gate import fetch_gate_eth_fear_latest
        # return fetch_gate_eth_fear_latest(trade_date, cfg=cfg)
        logger.debug("Gate ETH 恐慌 API 已预留，尚未接入")
        return None

    def fetch_history(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
        cfg: dict | None = None,
    ) -> list[FearSample]:
        if not self._enabled(cfg):
            return []
        # TODO: Gate ETH 历史回填
        return []


class OkxSolFearProvider(BaseCoinFearProvider):
    """
    预留：OKX SOL 单币种独立恐慌 API。
    实现 fetch_latest / fetch_history 后自动参与 SOL 多源校验。
    """

    name = "okx"
    supported_symbols = ("SOL",)

    def _enabled(self, cfg: dict | None = None) -> bool:
        cfg = cfg or load_config()
        ds = cfg.get("data_sources", {}).get("okx_fear", {})
        return bool(ds.get("enabled", False))

    def fetch_latest(
        self,
        symbol: str,
        trade_date: str,
        *,
        cfg: dict | None = None,
    ) -> FearSample | None:
        if not self._enabled(cfg):
            return None
        # TODO: 接入 OKX SOL 恐慌端点后在此解析 JSON → FearSample
        # from collectors.coin_fear_okx import fetch_okx_sol_fear_latest
        # return fetch_okx_sol_fear_latest(trade_date, cfg=cfg)
        logger.debug("OKX SOL 恐慌 API 已预留，尚未接入")
        return None

    def fetch_history(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
        cfg: dict | None = None,
    ) -> list[FearSample]:
        if not self._enabled(cfg):
            return []
        # TODO: OKX SOL 历史回填
        return []


# 注册表：主源在前，校验源在后
PRIMARY_PROVIDER = CfgiProvider()
VALIDATOR_PROVIDERS: tuple[BaseCoinFearProvider, ...] = (
    GateEthFearProvider(),
    OkxSolFearProvider(),
)


def validators_for_symbol(symbol: str, cfg: dict | None = None) -> list[BaseCoinFearProvider]:
    sym = symbol.upper()
    out: list[BaseCoinFearProvider] = []
    for p in VALIDATOR_PROVIDERS:
        if p.supports(sym):
            if isinstance(p, GateEthFearProvider) and p._enabled(cfg):
                out.append(p)
            elif isinstance(p, OkxSolFearProvider) and p._enabled(cfg):
                out.append(p)
    return out


def _merge_with_validators(
    primary: FearSample,
    validators: list[BaseCoinFearProvider],
    symbol: str,
    trade_date: str,
    *,
    cfg: dict | None = None,
) -> tuple[int, str]:
    """多源校验：偏差在阈值内则标注来源，超出仅记录告警仍用主源。"""
    if not _multi_source_enabled(cfg) or not validators:
        return primary.value, primary.source

    max_dev = _max_deviation(cfg)
    tags = [primary.source]
    for vp in validators:
        alt = vp.fetch_latest(symbol, trade_date, cfg=cfg)
        if alt is None:
            continue
        diff = abs(alt.value - primary.value)
        tags.append(alt.source)
        if diff > max_dev:
            logger.warning(
                "币种恐慌多源偏差 %s %s: %s=%d vs %s=%d (Δ%d > %d)，沿用主源",
                symbol,
                trade_date,
                primary.source,
                primary.value,
                alt.source,
                alt.value,
                diff,
                max_dev,
            )
        else:
            logger.info(
                "币种恐慌多源一致 %s %s: %s=%d %s=%d",
                symbol,
                trade_date,
                primary.source,
                primary.value,
                alt.source,
                alt.value,
            )
    return primary.value, "+".join(tags)


def resolve_coin_fear_value(
    symbol: str,
    trade_date: str,
    *,
    cfg: dict | None = None,
) -> tuple[int, str]:
    """
    解析单币种恐慌：CFGI 主源 → 多源校验 → 前日缓存 → 价格代理。
    """
    cfg = cfg or load_config()
    use_proxy = bool(
        cfg.get("data_sources", {}).get("cfgi", {}).get("use_proxy_fallback", True)
    )

    primary = PRIMARY_PROVIDER.fetch_latest(symbol, trade_date, cfg=cfg)
    if primary is not None:
        val, src = _merge_with_validators(
            primary,
            validators_for_symbol(symbol, cfg),
            symbol,
            trade_date,
            cfg=cfg,
        )
        return val, src

    prev = get_latest_before(symbol, trade_date)
    if prev and prev.get("value") is not None:
        logger.info(
            "币种恐慌 %s %s 使用缓存 %s",
            symbol,
            trade_date,
            prev["trade_date"],
        )
        return int(prev["value"]), f"cache:{prev['trade_date']}"

    if use_proxy:
        return proxy_coin_fear_for_date(symbol, trade_date), "proxy"

    raise RuntimeError("coin fear unavailable")


def fetch_history_primary(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    cfg: dict | None = None,
) -> list[FearSample]:
    """历史回填仅走主源 CFGI（Gate/OKX 历史接入后可在 backfill 中扩展）。"""
    return PRIMARY_PROVIDER.fetch_history(
        symbol, start_date=start_date, end_date=end_date, cfg=cfg
    )
