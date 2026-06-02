"""
程序入口
启动 Flask Web 服务；若 config.scheduler.enabled=true 则同时启动后台定时拉取。

用法：
    python main.py
"""

import atexit
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from core.config_loader import get_nested, load_config
from core.state_store import update_state
from core.scheduler_config import resolve_poll_interval
from scheduler.background_scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _ensure_dirs(cfg: dict) -> Path:
    log_dir = Path(get_nested(cfg, "storage", "log_dir", default="data/logs"))
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _init_idle_state() -> None:
    """进程启动时的初始展示（首轮拉取完成前）。"""
    update_state(
        fetch_log={
            "fetch_time": "—",
            "sources_summary": "后台定时任务启动后将立即执行首轮拉取…",
            "errors": [],
        },
    )


def main() -> None:
    cfg = load_config()
    web = cfg.get("web", {})
    sched = cfg.get("scheduler", {})

    host = web.get("host", "127.0.0.1")
    port = int(web.get("port", 5000))
    debug = bool(web.get("debug", False))

    _ensure_dirs(cfg)
    _init_idle_state()

    app = create_app()

    atexit.register(shutdown_scheduler)
    scheduler = start_scheduler(app)

    print("=" * 50)
    print("加密货币行情晴雨分析系统")
    print(f"访问地址: http://{host}:{port}/")
    print(f"健康检查: http://{host}:{port}/health")
    if sched.get("enabled", False):
        _, interval_label = resolve_poll_interval(sched)
        print(f"定时任务: 已启用，每 {interval_label} 拉取一次")
        refresh_sec = int(web.get("page_auto_refresh_seconds", 0) or 0)
        if refresh_sec > 0:
            print(f"页面自动刷新: 每 {refresh_sec} 秒")
        if scheduler:
            print("启动后将立即执行首轮拉取；若未开自动刷新请手动刷新页面")
    else:
        print("定时任务: 未启用（请在 config.yaml 设置 scheduler.enabled: true）")
    print("=" * 50)

    app.run(host=host, port=port, debug=debug, use_reloader=debug)


if __name__ == "__main__":
    main()
