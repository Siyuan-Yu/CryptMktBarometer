"""
Web 路由模块
首页展示三大板块骨架数据（第一步为占位数据，后续由定时任务填充）。
"""

from datetime import datetime

from flask import Blueprint, current_app, render_template

from core.market_rating import rating_css_class, rating_from_total_score

bp = Blueprint("main", __name__)


def _placeholder_score_categories() -> list[dict]:
    """
    板块 A：分项得分占位（第四步接入真实计分后替换）。
    权重：宏观 40、监管 20、资金 25、基本面 15
    """
    return [
        {
            "name": "宏观数据",
            "weight": 40,
            "score": None,
            "summary": "待对接：降息概率、CPI/PPI、美债10年期等（第三步）",
        },
        {
            "name": "全球监管政策",
            "weight": 20,
            "score": None,
            "summary": "待对接：各国法案、SEC/ETF 相关资讯（第三步）",
        },
        {
            "name": "资金链上数据",
            "weight": 25,
            "score": None,
            "summary": "待对接：ETF 流向、爆仓、合约持仓（第三步）",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": 15,
            "score": None,
            "summary": "待对接：质押数据、生态动态、Dune 指标（第三步）",
        },
    ]


def _placeholder_top_news() -> list[dict]:
    """板块 B：TOP10 资讯占位，第五步接入排序筛选。"""
    return []


def _placeholder_fetch_log() -> dict:
    """板块 C：本轮抓取日志占位。"""
    return {
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources_summary": "系统已启动，尚未执行首轮数据抓取（定时任务于第二步启用）。",
        "errors": [],
    }


@bp.route("/")
def index():
    """主仪表盘页面。"""
    cfg = current_app.config.get("APP_SETTINGS", {})
    categories = _placeholder_score_categories()
    total_score = None  # 无分项得分时不显示综合分

    rating_label = "待计算"
    rating_class = "rating-neutral"
    if total_score is not None:
        rating_label = rating_from_total_score(total_score)
        rating_class = rating_css_class(total_score)

    return render_template(
        "index.html",
        page_title="加密货币行情晴雨分析系统",
        categories=categories,
        total_score=total_score,
        rating_label=rating_label,
        rating_class=rating_class,
        top_news=_placeholder_top_news(),
        fetch_log=_placeholder_fetch_log(),
        web_host=cfg.get("web", {}).get("host", "127.0.0.1"),
        web_port=cfg.get("web", {}).get("port", 5000),
        scheduler_enabled=cfg.get("scheduler", {}).get("enabled", False),
        poll_interval=cfg.get("scheduler", {}).get("interval_minutes", 10),
    )


@bp.route("/health")
def health():
    """健康检查接口，便于确认服务已启动。"""
    return {"status": "ok", "message": "CryptMktBarometer is running"}
