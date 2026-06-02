"""
CryptMktBarometer Windows 桌面启动器（托盘 + 无控制台）

用于 PyInstaller 打包为单文件 exe；开发环境也可直接运行：
    python desktop_launcher.py

不修改 main.py 及业务模块源码，仅在启动时设置运行目录与路径补丁。
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 运行根目录：exe 所在目录（数据 / 配置 / 日志均写在此处）
# ---------------------------------------------------------------------------
def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    """PyInstaller 解压临时目录（只读资源）。"""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _app_root() -> Path:
    """用户数据根目录：exe 同目录。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = _app_root()
BUNDLE_ROOT = _bundle_root()

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)


def _patch_project_root() -> None:
    """将 config_loader.PROJECT_ROOT 指向 exe 目录，保证 data/ config/ 路径正确。"""
    import core.config_loader as cl

    cl.PROJECT_ROOT = APP_ROOT
    cl.DEFAULT_CONFIG_PATH = APP_ROOT / "config" / "config.yaml"
    cl.EXAMPLE_CONFIG_PATH = APP_ROOT / "config" / "config.example.yaml"
    cl._config_cache = None


def _bootstrap_runtime_files() -> None:
    """
    首次运行：从打包资源复制模板、静态资源、配置示例到 exe 同目录。
    不覆盖已存在的 config.yaml / data / 日志。
    """
    if not _is_frozen():
        return

    copies = [
        ("app/templates", APP_ROOT / "app" / "templates"),
        ("static", APP_ROOT / "static"),
    ]
    for rel, dest in copies:
        src = BUNDLE_ROOT / rel
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest)

    cfg_dir = APP_ROOT / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    example = BUNDLE_ROOT / "config" / "config.example.yaml"
    local_example = cfg_dir / "config.example.yaml"
    if example.exists() and not local_example.exists():
        shutil.copy2(example, local_example)
    target_cfg = cfg_dir / "config.yaml"
    if not target_cfg.exists():
        src_cfg = local_example if local_example.exists() else example
        if src_cfg.exists():
            shutil.copy2(src_cfg, target_cfg)

    log_dir = APP_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    db_parent = APP_ROOT / "data"
    db_parent.mkdir(parents=True, exist_ok=True)


_patch_project_root()
_bootstrap_runtime_files()

# 补丁完成后再导入业务模块
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from core.config_loader import get_nested, load_config  # noqa: E402
from core.state_store import update_state  # noqa: E402
from core.scheduler_config import resolve_poll_interval  # noqa: E402
from scheduler.background_scheduler import shutdown_scheduler, start_scheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(APP_ROOT / "data" / "logs" / "desktop.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("desktop_launcher")


class _ServerThread(threading.Thread):
    """在后台线程运行 Flask（禁用 debug / reloader）。"""

    def __init__(self, host: str, port: int) -> None:
        super().__init__(daemon=True, name="FlaskServer")
        self.host = host
        self.port = port
        self._httpd: Any = None
        self.app = None

    def run(self) -> None:
        cfg = load_config(reload=True)
        web = cfg.setdefault("web", {})
        web["debug"] = False

        log_dir = Path(get_nested(cfg, "storage", "log_dir", default="data/logs"))
        if not log_dir.is_absolute():
            log_dir = APP_ROOT / log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        update_state(
            fetch_log={
                "fetch_time": "—",
                "sources_summary": "桌面版已启动，等待首轮定时拉取…",
                "errors": [],
            },
        )

        self.app = create_app()
        self.app.config["APP_SETTINGS"] = load_config(reload=True)
        self.app.config["APP_SETTINGS"].setdefault("web", {})["debug"] = False

        start_scheduler(self.app)

        self._httpd = make_server(
            self.host,
            self.port,
            self.app,
            threaded=True,
        )
        logger.info("Flask 监听 http://%s:%s/", self.host, self.port)
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
        shutdown_scheduler()


_server: _ServerThread | None = None
_tray_icon: Any = None
_shutdown_event = threading.Event()


def _dashboard_url() -> str:
    cfg = load_config()
    host = cfg.get("web", {}).get("host", "127.0.0.1")
    port = int(cfg.get("web", {}).get("port", 5000))
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{port}/"


def open_dashboard(_icon: Any = None, _item: Any = None) -> None:
    webbrowser.open(_dashboard_url())


def quit_application(_icon: Any = None, _item: Any = None) -> None:
    logger.info("用户从托盘退出")
    global _tray_icon, _server
    _shutdown_event.set()
    try:
        from floating_integration import shutdown_with_desktop

        shutdown_with_desktop()
    except Exception:
        pass
    if _server:
        _server.shutdown()
    if _tray_icon:
        _tray_icon.stop()
    os._exit(0)


def _load_tray_image():
    from PIL import Image, ImageDraw

    candidates = [
        APP_ROOT / "packaging" / "icon.ico",
        BUNDLE_ROOT / "packaging" / "icon.ico",
        BUNDLE_ROOT / "icon.ico",
    ]
    for path in candidates:
        if path.exists():
            return Image.open(path).convert("RGBA")

    size = 64
    img = Image.new("RGBA", (size, size), (37, 99, 235, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=(255, 255, 255, 230))
    draw.text((18, 20), "晴", fill=(37, 99, 235, 255))
    return img


def _run_tray() -> None:
    import pystray

    global _tray_icon
    def _tray_show_float(_icon: Any = None, _item: Any = None) -> None:
        try:
            from floating_integration import show_floating_with_desktop

            show_floating_with_desktop()
        except Exception as exc:
            logger.warning("显示悬浮球: %s", exc)

    menu = pystray.Menu(
        pystray.MenuItem("打开晴雨表面板", open_dashboard, default=True),
        pystray.MenuItem("显示悬浮球", _tray_show_float),
        pystray.MenuItem("退出程序", quit_application),
    )
    _tray_icon = pystray.Icon(
        "CryptMktBarometer",
        _load_tray_image(),
        "加密货币行情晴雨表",
        menu,
    )
    _tray_icon.run()


def main() -> None:
    global _server

    cfg = load_config(reload=True)
    web = cfg.get("web", {})
    host = web.get("host", "127.0.0.1")
    port = int(web.get("port", 5000))

    _server = _ServerThread(host, port)
    _server.start()

    for _ in range(50):
        if _server._httpd is not None:
            break
        time.sleep(0.1)

    time.sleep(0.3)
    webbrowser.open(_dashboard_url())

    try:
        from floating_integration import launch_with_desktop

        launch_with_desktop(_dashboard_url())
    except Exception as exc:
        logger.warning("悬浮窗未启动: %s", exc)

    sched = cfg.get("scheduler", {})
    if sched.get("enabled", False):
        _, label = resolve_poll_interval(sched)
        logger.info("定时拉取已启用：每 %s", label)

    _run_tray()


if __name__ == "__main__":
    main()
