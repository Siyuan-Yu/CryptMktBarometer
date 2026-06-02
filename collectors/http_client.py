"""
HTTP 请求工具
"""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT = 15
DEFAULT_HEADERS = {
    "User-Agent": "CryptMktBarometer/1.0 (local research)",
    "Accept": "application/json, application/xml, text/xml, */*",
}


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
