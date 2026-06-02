"""
Web 路由模块
首页从内存状态读取定时任务最新一轮抓取结果并渲染三大板块。
"""

from flask import Blueprint, current_app, jsonify, render_template, request

from core.config_loader import load_config
from core.market_rating import rating_css_class, rating_from_total_score
from core.scheduler_config import resolve_poll_interval
from core.state_store import get_state

bp = Blueprint("main", __name__)


def _default_fetch_log() -> dict:
    return {
        "fetch_time": "—",
        "sources_summary": "定时任务已启用，等待首轮拉取完成…",
        "errors": [],
    }


def _default_categories() -> list[dict]:
    return [
        {
            "name": "宏观数据",
            "weight": 40,
            "score": None,
            "summary": "等待定时任务拉取（第三步对接数据源）",
        },
        {
            "name": "全球监管政策",
            "weight": 20,
            "score": None,
            "summary": "等待定时任务拉取（第三步对接数据源）",
        },
        {
            "name": "资金链上数据",
            "weight": 25,
            "score": None,
            "summary": "等待定时任务拉取（第三步对接数据源）",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": 15,
            "score": None,
            "summary": "等待定时任务拉取（第三步对接数据源）",
        },
    ]


@bp.route("/")
def index():
    """主仪表盘页面。"""
    cfg = current_app.config.get("APP_SETTINGS", {})
    state = get_state()

    categories = state.categories or _default_categories()
    total_score = state.total_score
    top_news = state.top_news or []
    fetch_log = state.fetch_log or _default_fetch_log()

    rating_label = fetch_log.get("rating_label") or "待计算"
    rating_class = "rating-neutral"
    if total_score is not None:
        rating_label = rating_from_total_score(total_score)
        rating_class = rating_css_class(total_score)

    last_fetch_display = "—"
    if state.last_fetch_time:
        last_fetch_display = state.last_fetch_time.strftime("%Y-%m-%d %H:%M:%S")

    sched_cfg = cfg.get("scheduler", {})
    _, poll_interval_label = resolve_poll_interval(sched_cfg)
    page_refresh = int(cfg.get("web", {}).get("page_auto_refresh_seconds", 0) or 0)

    return render_template(
        "index.html",
        page_title="加密货币行情晴雨分析系统",
        categories=categories,
        total_score=total_score,
        rating_label=rating_label,
        rating_class=rating_class,
        top_news=top_news,
        fetch_log=fetch_log,
        web_host=cfg.get("web", {}).get("host", "127.0.0.1"),
        web_port=cfg.get("web", {}).get("port", 5000),
        scheduler_enabled=sched_cfg.get("enabled", False),
        poll_interval_label=poll_interval_label,
        page_auto_refresh_seconds=page_refresh,
        fetch_count=state.fetch_count,
        is_fetching=state.is_fetching,
        last_fetch_time=last_fetch_display,
        weight_optimizer=state.weight_optimizer or {},
    )


@bp.route("/api/backtest", methods=["GET", "POST"])
def api_backtest():
    """
    运行历史回测。
    参数：start=YYYY-MM-DD&end=YYYY-MM-DD
    示例：/api/backtest?start=2024-01-01&end=2025-05-31
    """
    cfg = load_config()
    opt = cfg.get("weight_optimizer", {}).get("backtest", {})
    start = request.values.get("start") or opt.get("default_start", "2024-01-01")
    end = request.values.get("end") or opt.get("default_end", "2025-05-31")

    from weight_optimizer import run_backtest, run_weight_pipeline

    result = run_backtest(start, end, cfg)
    run_weight_pipeline(cfg)
    return jsonify(result.summary_dict())


@bp.route("/health")
def health():
    """健康检查：含定时任务与最近拉取信息。"""
    cfg = current_app.config.get("APP_SETTINGS", {})
    state = get_state()
    sched = cfg.get("scheduler", {})
    interval_seconds, interval_label = resolve_poll_interval(sched)

    return jsonify(
        {
            "status": "ok",
            "message": "CryptMktBarometer is running",
            "scheduler": {
                "enabled": sched.get("enabled", False),
                "interval_seconds": interval_seconds,
                "interval_label": interval_label,
                "interval_minutes": sched.get("interval_minutes", 10),
                "is_fetching": state.is_fetching,
                "fetch_count": state.fetch_count,
                "last_fetch_time": (
                    state.last_fetch_time.isoformat() if state.last_fetch_time else None
                ),
            },
            "score": {
                "total": state.total_score,
                "rating": (
                    rating_from_total_score(state.total_score)
                    if state.total_score is not None
                    else None
                ),
            },
        }
    )
