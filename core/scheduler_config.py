"""
定时任务间隔配置解析
测试阶段可用 interval_seconds；正式环境使用 interval_minutes。
"""


def resolve_poll_interval(sched_cfg: dict) -> tuple[int, str]:
    """
    返回 (调度器间隔秒数, 页面展示文案)。
    interval_seconds > 0 时优先于 interval_minutes。
    """
    sec = sched_cfg.get("interval_seconds")
    if sec is not None and int(sec) > 0:
        seconds = max(1, int(sec))
        return seconds, f"{seconds} 秒"

    minutes = max(1, int(sched_cfg.get("interval_minutes", 10)))
    return minutes * 60, f"{minutes} 分钟"
