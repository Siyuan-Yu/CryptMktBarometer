"""
链上客观数据采集：每 4 小时同步一次，写入 onchain_snapshots。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from collectors.onchain_apis import (
    fetch_btc_hashrate_latest,
    fetch_eth_onchain_stats,
    fetch_fear_greed,
    fetch_global_market_cmc,
    fetch_global_market_coingecko,
    fetch_glassnode_metric,
    fetch_sol_tvl_chg_pct,
)
from core.config_loader import load_config
from scoring.onchain_objective import compute_adjustments
from storage.onchain_db import (
    OnchainSnapshot,
    get_previous_snapshot,
    init_schema,
    insert_snapshot,
    last_fetch_age_hours,
)

logger = logging.getLogger(__name__)


@dataclass
class OnchainCollectResult:
    snapshot: OnchainSnapshot | None = None
    skipped: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.skipped and self.snapshot:
            return f"链上客观(缓存) {self.snapshot.summary}"
        if self.snapshot:
            return self.snapshot.summary
        return "链上客观数据未就绪"


def _should_sync(cfg: dict) -> bool:
    hours = float(cfg.get("collector", {}).get("onchain_sync_hours", 4))
    age = last_fetch_age_hours()
    return age is None or age >= hours


def collect_onchain(*, force: bool = False) -> OnchainCollectResult:
    """
    拉取免费链上 API 并持久化；默认 4 小时内不重复请求。
    """
    cfg = load_config()
    ds = cfg.get("data_sources", {}).get("onchain", {})
    if not any(ds.get(k, False) for k in ("fear_greed", "glassnode_signals", "coinmarketcap_global", "eth_staking", "solana_official")):
        return OnchainCollectResult(skipped=True, errors=["链上数据源已全部关闭"])

    init_schema()
    if not force and not _should_sync(cfg):
        from storage.onchain_db import get_latest_snapshot

        prev = get_latest_snapshot()
        return OnchainCollectResult(snapshot=prev, skipped=True)

    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 15))
    api = cfg.get("api_keys", {})
    errors: list[str] = []
    raw: dict = {}

    fg_val, fg_cls, err = (None, "", None)
    if ds.get("fear_greed", True):
        fg_val, fg_cls, err = fetch_fear_greed(timeout=timeout)
        if err:
            errors.append(f"恐惧贪婪:{err}")

    hr_chg, err = (None, None)
    if ds.get("glassnode_signals", True):
        hr_chg, err = fetch_btc_hashrate_latest(timeout=timeout)
        if err:
            errors.append(f"BTC哈希率:{err}")
        gn_key = api.get("glassnode", "")
        if gn_key:
            v, gerr = fetch_glassnode_metric(
                gn_key, "mining/miners_outflow_sum", asset="BTC", timeout=timeout
            )
            if v is not None:
                raw["glassnode_miners_outflow"] = v
            elif gerr:
                errors.append(f"Glassnode:{gerr}")

    eth_vol, eth_large, err = (None, None, None)
    if ds.get("eth_staking", True):
        eth_vol, eth_large, err = fetch_eth_onchain_stats(timeout=timeout)
        if err:
            errors.append(f"ETH链上:{err}")

    sol_tvl, err = (None, None)
    if ds.get("solana_official", True):
        sol_tvl, err = fetch_sol_tvl_chg_pct(timeout=timeout)
        if err:
            errors.append(f"SOL TVL:{err}")

    mcap_chg, vol_usd, err = (None, None, None)
    if ds.get("coinmarketcap_global", True):
        cmc_key = api.get("coinmarketcap", "")
        if cmc_key:
            mcap_chg, vol_usd, err = fetch_global_market_cmc(cmc_key, timeout=timeout)
        if mcap_chg is None:
            mcap_chg, vol_usd, err2 = fetch_global_market_coingecko(timeout=timeout)
            if err2 and err:
                errors.append(f"全球宏观:{err}; CoinGecko:{err2}")
            elif err2:
                errors.append(f"CoinGecko:{err2}")
        elif err:
            errors.append(f"CMC:{err}")
        raw["volume_usd"] = vol_usd

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    snap = OnchainSnapshot(
        fetched_at=now,
        fear_greed=fg_val,
        fear_greed_class=fg_cls,
        btc_hashrate_chg_pct=hr_chg,
        eth_volume_24h_usd=eth_vol,
        eth_largest_tx_24h_usd=eth_large,
        sol_tvl_chg_pct=sol_tvl,
        market_cap_chg_24h_pct=mcap_chg,
        etf_flow_proxy_pct=mcap_chg,
        raw_json=json.dumps(raw, ensure_ascii=False)[:4000],
        errors=errors,
    )
    prev = get_previous_snapshot(now)
    snap = compute_adjustments(snap, prev=prev)
    insert_snapshot(snap)
    logger.info(
        "链上客观快照 %s | BTC%+s ETH%+s SOL%+s",
        now,
        snap.adj_btc,
        snap.adj_eth,
        snap.adj_sol,
    )
    return OnchainCollectResult(snapshot=snap, errors=errors)
