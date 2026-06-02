"""
Flask 应用工厂
创建 Web 应用并注册路由、静态资源。
"""

from flask import Flask

from core.config_loader import PROJECT_ROOT, load_config


def create_app() -> Flask:
    """创建并配置 Flask 应用实例。"""
    cfg = load_config()

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "app" / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
        static_url_path="/static",
    )

    # 将配置挂到 app，便于路由中读取
    app.config["APP_SETTINGS"] = cfg

    from app.routes import bp as main_bp

    app.register_blueprint(main_bp)

    return app
