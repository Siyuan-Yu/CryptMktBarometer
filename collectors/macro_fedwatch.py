"""
CME FedWatch 降息/加息概率（无官方免费 API）
当前方案：在已配置 FRED Key 时，用联邦基金利率与 2Y 国债收益率差作简易「政策预期」参考；
完整 FedWatch 概率页后续可接爬虫或付费源。
"""

from __future__ import annotations

import logging

from collectors.macro_fred import fetch_series_latest

logger = logging.getLogger(__name__)


def fetch_policy_expectation_proxy(
    fred_api_key: str,
    *,
    timeout: int = 15,
) -> tuple[str | None, str | None]:
    """
    简易政策预期描述（非 CME 官方概率）。
    :return: (描述文案, 错误信息)
    """
    if not fred_api_key or not str(fred_api_key).strip():
        return None, "CME FedWatch：无免费稳定接口；请配置 api_keys.fred 以启用利率预期 proxy"

    ff, _, err1 = fetch_series_latest(fred_api_key, "FEDFUNDS", timeout=timeout)
    y2, _, err2 = fetch_series_latest(fred_api_key, "DGS2", timeout=timeout)

    if err1 and err2:
        return None, f"CME FedWatch proxy：{err1}; {err2}"

    parts: list[str] = []
    if ff is not None:
        parts.append(f"联邦基金利率 {ff:.2f}%")
    if y2 is not None:
        parts.append(f"2Y国债 {y2:.2f}%")
    if ff is not None and y2 is not None:
        spread = y2 - ff
        if spread < 0:
            hint = "收益率曲线偏倒挂，市场偏降息/衰退预期"
        elif spread < 0.5:
            hint = "短端利差偏窄，政策预期偏谨慎"
        else:
            hint = "短端利差正常，政策预期相对平稳"
        parts.append(hint)

    if not parts:
        return None, "CME FedWatch proxy：数据不足"

    return "；".join(parts) + "（FRED proxy，非 CME 官方概率）", None
