"""
美国财政部每日 par yield curve（无需 API Key）
官方 XML：https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

_XML_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
}


def _yield_curve_url(year: int | None = None) -> str:
    y = year or datetime.now().year
    return (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        f"?data=daily_treasury_yield_curve&field_tdr_date_value={y}"
    )


def fetch_10y_from_treasury(*, timeout: int = 20) -> tuple[float | None, float | None, str | None]:
    """
    从财政部 XML 获取最近两个交易日的 10 年期收益率（%）。
    :return: (最新值, 前一交易日值, 错误)
    """
    headers = {"User-Agent": "CryptMktBarometer/1.0", "Accept": "application/atom+xml"}
    year = datetime.now().year

    for attempt_year in (year, year - 1):
        url = _yield_curve_url(attempt_year)
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            logger.warning("Treasury XML %s 失败: %s", attempt_year, exc)
            continue

        pairs: list[tuple[str, float]] = []
        for entry in root.findall("atom:entry", _XML_NS):
            props = entry.find("atom:content/m:properties", _XML_NS)
            if props is None:
                continue
            date_el = props.find("d:NEW_DATE", _XML_NS)
            y10_el = props.find("d:BC_10YEAR", _XML_NS)
            if y10_el is None or not y10_el.text:
                continue
            try:
                pairs.append((date_el.text if date_el is not None else "", float(y10_el.text)))
            except ValueError:
                continue

        if not pairs:
            continue

        pairs.sort(key=lambda x: x[0])
        latest = pairs[-1][1]
        prev = pairs[-2][1] if len(pairs) > 1 else None
        return latest, prev, None

    return None, None, "财政部10Y：未能解析当年/去年 yield curve XML"
