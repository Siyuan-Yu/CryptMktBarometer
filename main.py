"""
程序入口
启动 Flask Web 服务，供本机浏览器访问仪表盘页面。

用法：
    python main.py

或在项目根目录：
    pip install -r requirements.txt
    python main.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from core.config_loader import get_nested, load_config


def main() -> None:
    cfg = load_config()
    web = cfg.get("web", {})

    host = web.get("host", "127.0.0.1")
    port = int(web.get("port", 5000))
    debug = bool(web.get("debug", False))

    # 确保日志目录存在
    log_dir = Path(get_nested(cfg, "storage", "log_dir", default="data/logs"))
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    app = create_app()

    print("=" * 50)
    print("加密货币行情晴雨分析系统")
    print(f"访问地址: http://{host}:{port}/")
    print(f"健康检查: http://{host}:{port}/health")
    print("=" * 50)

    app.run(host=host, port=port, debug=debug, use_reloader=debug)


if __name__ == "__main__":
    main()
