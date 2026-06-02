"""
悬浮窗与 desktop_launcher 的薄集成层（仅几行调用，便于维护）
"""

from __future__ import annotations

import logging

logger = logging.getLogger("floating_integration")


def launch_with_desktop(dashboard_url: str) -> bool:
    """Flask 就绪后启动悬浮窗。成功返回 True。"""
    try:
        from floating_dashboard import start_floating_window

        base = dashboard_url.rstrip("/")
        start_floating_window(base)
        return True
    except Exception as exc:
        logger.warning("悬浮窗启动失败（可忽略）: %s", exc)
        return False


def show_floating_with_desktop() -> None:
    """托盘菜单：显示已隐藏的悬浮球。"""
    try:
        from floating_dashboard import show_floating_window

        show_floating_window()
    except Exception as exc:
        logger.debug("显示悬浮球失败: %s", exc)


def shutdown_with_desktop() -> None:
    """托盘退出时关闭悬浮窗。"""
    try:
        from floating_dashboard import stop_floating_window

        stop_floating_window()
    except Exception:
        pass
