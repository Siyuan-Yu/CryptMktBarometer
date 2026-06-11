"""
Web 路由模块
首页从内存状态读取定时任务最新一轮抓取结果并渲染各板块。
"""

from datetime import date

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
            "weight": 30,
            "score": None,
            "summary": "等待定时任务拉取",
        },
        {
            "name": "全球监管政策",
            "weight": 30,
            "score": None,
            "summary": "等待定时任务拉取",
        },
        {
            "name": "资金链上数据",
            "weight": 35,
            "score": None,
            "summary": "等待定时任务拉取",
        },
        {
            "name": "ETH/SOL 币种基本面",
            "weight": 5,
            "score": None,
            "summary": "等待定时任务拉取",
        },
    ]


def _dashboard_payload(cfg: dict) -> dict:
    """组装 API / 页面共用的仪表盘 JSON。"""
    state = get_state()
    categories = state.categories or _default_categories()
    total_score = state.total_score
    fetch_log = state.fetch_log or _default_fetch_log()

    rating_label = fetch_log.get("rating_label") or "待计算"
    rating_class = "rating-neutral"
    if total_score is not None:
        rating_label = rating_from_total_score(total_score)
        rating_class = rating_css_class(total_score)

    last_fetch_display = "—"
    if state.last_fetch_time:
        last_fetch_display = state.last_fetch_time.strftime("%Y-%m-%d %H:%M:%S")

    wo = state.weight_optimizer or {}
    opt = cfg.get("weight_optimizer", {})
    bt_cfg = opt.get("backtest", {})
    web_cfg = cfg.get("web", {})

    return {
        "categories": categories,
        "total_score": total_score,
        "rating_label": rating_label,
        "rating_class": rating_class,
        "top_news": state.top_news or [],
        "btc_news": state.btc_news or [],
        "sol_news": state.sol_news or [],
        "eth_news": state.eth_news or [],
        "macro_news": state.macro_news or [],
        "fetch_log": fetch_log,
        "fetch_count": state.fetch_count,
        "is_fetching": state.is_fetching,
        "last_fetch_time": last_fetch_display,
        "weight_optimizer": wo,
        "recalc_interval_hours": int(opt.get("recalc_interval_hours", 6)),
        "backtest_default_start": bt_cfg.get("default_start", "2025-01-01"),
        "backtest_default_end": date.today().isoformat(),
        "price_refresh_seconds": int(web_cfg.get("price_refresh_seconds", 5) or 5),
        "dashboard_refresh_seconds": int(
            web_cfg.get("dashboard_refresh_seconds", 30) or 30
        ),
    }


@bp.route("/")
def index():
    """主仪表盘页面。"""
    cfg = current_app.config.get("APP_SETTINGS", {})
    payload = _dashboard_payload(cfg)

    sched_cfg = cfg.get("scheduler", {})
    _, poll_interval_label = resolve_poll_interval(sched_cfg)
    web_cfg = cfg.get("web", {})
    page_refresh = int(web_cfg.get("page_auto_refresh_seconds", 0) or 0)
    dashboard_refresh = int(web_cfg.get("dashboard_refresh_seconds", 30) or 30)
    price_refresh = int(web_cfg.get("price_refresh_seconds", 5) or 5)

    return render_template(
        "index.html",
        page_title="加密货币行情晴雨分析系统",
        categories=payload["categories"],
        total_score=payload["total_score"],
        rating_label=payload["rating_label"],
        rating_class=payload["rating_class"],
        top_news=payload["top_news"],
        btc_news=payload["btc_news"],
        sol_news=payload["sol_news"],
        eth_news=payload["eth_news"],
        macro_news=payload["macro_news"],
        fetch_log=payload["fetch_log"],
        web_host=web_cfg.get("host", "127.0.0.1"),
        web_port=web_cfg.get("port", 5000),
        scheduler_enabled=sched_cfg.get("enabled", False),
        poll_interval_label=poll_interval_label,
        page_auto_refresh_seconds=page_refresh,
        dashboard_refresh_seconds=dashboard_refresh,
        price_refresh_seconds=price_refresh,
        fetch_count=payload["fetch_count"],
        is_fetching=payload["is_fetching"],
        last_fetch_time=payload["last_fetch_time"],
        weight_optimizer=payload["weight_optimizer"],
        recalc_interval_hours=payload["recalc_interval_hours"],
        backtest_default_start=payload["backtest_default_start"],
    )


@bp.route("/api/dashboard")
def api_dashboard():
    """前端定时拉取：晴雨表、资讯、权重等（默认 30 秒）。"""
    cfg = current_app.config.get("APP_SETTINGS", {}) or load_config()
    return jsonify(_dashboard_payload(cfg))


@bp.route("/api/prices")
def api_prices():
    """实时价格（默认 5 秒轮询，服务端短缓存）。"""
    cfg = current_app.config.get("APP_SETTINGS", {}) or load_config()
    cache_sec = float(cfg.get("web", {}).get("price_cache_seconds", 4) or 4)
    timeout = int(cfg.get("collector", {}).get("request_timeout_sec", 10))

    from collectors.fear_greed_ticker import get_cached_fear_greed
    from collectors.price_ticker import get_cached_prices

    data = get_cached_prices(cache_seconds=cache_sec, timeout=timeout)
    fg_cache = float(cfg.get("web", {}).get("fear_greed_cache_seconds", 60) or 60)
    data["fear_greed"] = get_cached_fear_greed(
        cache_seconds=fg_cache,
        timeout=timeout,
    )
    from storage.coin_fear_db import get_all_latest

    data["coin_fear"] = get_all_latest()
    return jsonify(data)


@bp.route("/api/score-history")
def api_score_history():
    """四品种分数历史（2026 年初至今，来自 score_history.csv）。"""
    since = request.values.get("since", "2025-01-01")
    from core.score_history import build_score_history_payload

    return jsonify(build_score_history_payload(since=since))


@bp.route("/api/export-score-history")
def api_export_score_history():
    """导出四品种 4 小时粒度分数历史 CSV（2026 年初至今）。"""
    from flask import Response

    from core.score_export import _EXPORT_FILENAME, build_score_history_csv

    since = request.values.get("since", "2025-01-01")
    csv_body = build_score_history_csv(since=since)
    return Response(
        csv_body,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_EXPORT_FILENAME}"',
        },
    )


@bp.route("/api/backtest", methods=["GET", "POST"])
def api_backtest():
    """运行历史回测。参数：start=YYYY-MM-DD&end=YYYY-MM-DD"""
    cfg = load_config()
    opt = cfg.get("weight_optimizer", {}).get("backtest", {})
    start = request.values.get("start") or opt.get("default_start", "2025-01-01")
    end = request.values.get("end") or date.today().isoformat()

    try:
        from weight_optimizer import run_backtest, run_weight_pipeline

        result = run_backtest(start, end, cfg)
        run_weight_pipeline(cfg)
        out = result.summary_dict()
        out["ok"] = True
        return jsonify(out)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


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

