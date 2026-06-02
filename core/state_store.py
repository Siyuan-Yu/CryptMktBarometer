"""
应用内存状态存储
定时任务写入最新一轮抓取结果，Web 路由读取并渲染页面。
线程安全，供后台调度线程与 Flask 请求线程共享。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class DashboardState:
    """仪表盘当前展示数据（与三大板块对应）。"""

    categories: list[dict[str, Any]] = field(default_factory=list)
    total_score: float | None = None
    top_news: list[dict[str, Any]] = field(default_factory=list)
    fetch_log: dict[str, Any] = field(default_factory=dict)
    last_fetch_time: datetime | None = None
    fetch_count: int = 0
    is_fetching: bool = False
    weight_optimizer: dict[str, Any] = field(default_factory=dict)


_lock = Lock()
_state = DashboardState()


def get_state() -> DashboardState:
    """返回当前状态的深拷贝，避免渲染时被后台线程修改。"""
    with _lock:
        return copy.deepcopy(_state)


def update_state(
    *,
    categories: list[dict[str, Any]] | None = None,
    total_score: float | None = None,
    top_news: list[dict[str, Any]] | None = None,
    fetch_log: dict[str, Any] | None = None,
    last_fetch_time: datetime | None = None,
    fetch_count: int | None = None,
    is_fetching: bool | None = None,
    weight_optimizer: dict[str, Any] | None = None,
) -> None:
    """按字段更新内存状态（仅更新传入的非 None 字段）。"""
    global _state
    with _lock:
        if categories is not None:
            _state.categories = categories
        if total_score is not None:
            _state.total_score = total_score
        if top_news is not None:
            _state.top_news = top_news
        if fetch_log is not None:
            _state.fetch_log = fetch_log
        if last_fetch_time is not None:
            _state.last_fetch_time = last_fetch_time
        if fetch_count is not None:
            _state.fetch_count = fetch_count
        if is_fetching is not None:
            _state.is_fetching = is_fetching
        if weight_optimizer is not None:
            _state.weight_optimizer = weight_optimizer


def set_fetching(flag: bool) -> None:
    with _lock:
        _state.is_fetching = flag


def increment_fetch_count() -> int:
    with _lock:
        _state.fetch_count += 1
        return _state.fetch_count
