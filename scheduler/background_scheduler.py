"""
后台定时调度器
使用 APScheduler 按 config 中的间隔周期执行数据拉取（支持秒/分钟）。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from collectors.fetch_runner import run_data_fetch
from core.config_loader import load_config
from core.scheduler_config import resolve_poll_interval

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def should_run_scheduler_in_this_process(debug: bool) -> bool:
    """
    Flask debug 重载会启动父子两个进程，仅在子进程启动调度器，避免重复执行。
    非 debug 模式下始终启动。
    """
    if not debug:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def start_scheduler(app: Flask | None = None) -> BackgroundScheduler | None:
    """
    启动后台定时任务：立即执行首轮拉取，之后按间隔轮询。
    :return: 调度器实例；未启用或不应在本进程启动时返回 None
    """
    global _scheduler

    cfg = load_config()
    sched_cfg = cfg.get("scheduler", {})
    if not sched_cfg.get("enabled", False):
        logger.info("定时任务未启用（config.scheduler.enabled=false）")
        return None

    web_debug = bool(cfg.get("web", {}).get("debug", False))
    if not should_run_scheduler_in_this_process(web_debug):
        logger.debug("当前为 Flask 重载父进程，跳过调度器启动")
        return None

    if _scheduler is not None and _scheduler.running:
        logger.warning("调度器已在运行，跳过重复启动")
        return _scheduler

    interval_seconds, interval_label = resolve_poll_interval(sched_cfg)

    _scheduler = BackgroundScheduler(daemon=True, timezone="Asia/Shanghai")
    _scheduler.add_job(
        run_data_fetch,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="data_fetch_job",
        name="全渠道数据拉取",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    _scheduler.start()
    logger.info("定时任务已启动，间隔 %s", interval_label)

    # 启动后立即执行首轮，无需等待第一个周期
    _scheduler.add_job(
        run_data_fetch,
        id="data_fetch_startup",
        name="启动首轮拉取",
        replace_existing=True,
    )

    opt = cfg.get("weight_optimizer", {})
    if opt.get("enabled", True):
        recalc_h = int(opt.get("recalc_interval_hours", 6))
        from weight_optimizer import run_weight_pipeline

        _scheduler.add_job(
            run_weight_pipeline,
            trigger=IntervalTrigger(hours=recalc_h),
            id="weight_recalc_job",
            name="动态权重重算",
            replace_existing=True,
            max_instances=1,
        )
        _scheduler.add_job(
            run_weight_pipeline,
            id="weight_recalc_startup",
            name="启动权重管线",
            replace_existing=True,
        )
        logger.info("动态权重任务已启动，每 %d 小时重算", recalc_h)

    if app is not None:
        app.config["SCHEDULER"] = _scheduler

    return _scheduler


def shutdown_scheduler() -> None:
    """优雅关闭调度器（进程退出时调用）。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("定时任务已停止")
    _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler
