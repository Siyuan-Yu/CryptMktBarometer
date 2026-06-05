"""
数据拉取编排模块
拉取各数据源后调用 scoring 模块计算分项分与综合总分。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from collectors.funding_collect import collect_funding
from collectors.macro_collect import collect_macro
from collectors.community_collect import collect_community
from collectors.onchain_collect import collect_onchain
from scoring.symbol_scores import compute_live_normalized_scores
from collectors.news_collect import collect_news_split
from collectors.news_display import prepare_all_news_views
from core.config_loader import load_config
from core.state_store import increment_fetch_count, set_fetching, update_state
from scoring.engine import compute_scores
from storage.csv_logger import (
    append_fetch_log_row,
    append_news_snapshot,
    append_score_history,
)
from storage.score_history_db import upsert_4h_scores

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """单轮拉取结果。"""

    started_at: datetime
    finished_at: datetime
    sources_summary: str
    errors: list[str] = field(default_factory=list)
    categories: list[dict[str, Any]] = field(default_factory=list)
    top_news: list[dict[str, Any]] = field(default_factory=list)
    total_score: float | None = None
    rating_label: str = "待计算"

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def _onchain_pending_summary(cfg: dict[str, Any]) -> str:
    ds = cfg.get("data_sources", {}).get("onchain", {})
    if not any(ds.values()):
        return "链上数据源已全部关闭"
    enabled = [k for k, v in ds.items() if v]
    return f"待对接：{', '.join(enabled)}"


def run_data_fetch() -> FetchResult:
    """执行一轮全渠道数据拉取并计分。"""
    started_at = datetime.now()
    set_fetching(True)
    logger.info("开始本轮数据拉取 @ %s", started_at.strftime("%Y-%m-%d %H:%M:%S"))

    errors: list[str] = []
    try:
        cfg = load_config(reload=True)
        round_no = increment_fetch_count()

        crypto_news, macro_news_items, news_summary_lines, news_errors = (
            collect_news_split(cfg)
        )
        all_news = crypto_news + macro_news_items
        errors.extend(news_errors)
        news_views = prepare_all_news_views(
            crypto_news,
            macro_news_items,
            top_limit=10,
            category_limit=20,
        )
        top_news = news_views["top"]
        btc_news = news_views["btc"]
        sol_news = news_views["sol"]
        eth_news = news_views["eth"]
        macro_news = news_views["macro"]

        macro = collect_macro(cfg)
        errors.extend(macro.errors)

        funding = collect_funding(cfg)
        errors.extend(funding.errors)

        onchain_result = collect_onchain()
        onchain_connected = onchain_result.snapshot is not None
        onchain_summary = (
            onchain_result.summary
            if onchain_connected
            else _onchain_pending_summary(cfg)
        )
        errors.extend(onchain_result.errors)

        score_result = compute_scores(
            macro=macro,
            funding=funding,
            all_news=all_news,
            macro_data_summary=macro.category_summary,
            funding_data_summary=funding.category_summary,
            onchain_connected=onchain_connected,
            onchain_data_summary=onchain_summary,
        )

        community_result = collect_community()
        errors.extend(community_result.errors)

        finished_at = datetime.now()
        norm_scores = compute_live_normalized_scores(
            all_news=all_news,
            macro=macro,
            funding=funding,
            onchain_snap=onchain_result.snapshot,
            community_lanes=community_result.lanes,
            fetch_time=finished_at,
        )
        from core.market_rating import rating_from_total_score

        score_result.total_score = norm_scores["BTC"]
        score_result.rating_label = rating_from_total_score(
            score_result.total_score
        )
        layer_note = (
            f"｜分层60/30/10 BTC{norm_scores['BTC']:.0f}"
            f"/ETH{norm_scores['ETH']:.0f}/SOL{norm_scores['SOL']:.0f}"
        )
        for cat in score_result.categories:
            if cat.get("name") == "宏观数据":
                cat["summary"] = str(cat.get("summary", "")) + layer_note
                break

        opt_cfg = cfg.get("weight_optimizer", {})
        if opt_cfg.get("enabled", True):
            try:
                import weight_optimizer as wo

                wo.register_top_news(all_news, top_news)
                wo.measure_pending_impacts()
                weights = wo.compute_dynamic_weights(cfg)
                if opt_cfg.get("use_dynamic_weights", True):
                    _total_dyn, cats_dyn = wo.apply_dynamic_total(
                        score_result.categories, weights
                    )
                    score_result.categories = cats_dyn
                inf7, inf30 = wo.get_dual_module_influence()
                recalc_h = int(opt_cfg.get("recalc_interval_hours", 6))
                next_at = (
                    __import__("datetime").datetime.now()
                    + __import__("datetime").timedelta(hours=recalc_h)
                ).strftime("%Y-%m-%d %H:%M:%S")
                wo._persist_optimizer_state(
                    {
                        "weights": weights,
                        "influence_7": inf7,
                        "influence_30": inf30,
                        "price_sync": {},
                        "impacts_updated": wo.measure_pending_impacts(),
                        "next_recalc_at": next_at,
                    }
                )
            except Exception as exc:
                logger.warning("动态权重处理跳过: %s", exc)

        summary_parts = [f"第 {round_no} 轮拉取"]
        if news_summary_lines:
            summary_parts.append("资讯[" + "；".join(news_summary_lines) + "]")
        if macro.summary_lines:
            summary_parts.append("宏观[" + "；".join(macro.summary_lines) + "]")
        if funding.summary_lines:
            summary_parts.append("资金[" + "；".join(funding.summary_lines) + "]")
        summary_parts.append(
            f"综合{score_result.total_score:.1f}分·{score_result.rating_label}"
        )
        if top_news:
            summary_parts.append(f"TOP10 {len(top_news)} 条")

        sources_summary = "。".join(summary_parts) + "。"

        result = FetchResult(
            started_at=started_at,
            finished_at=finished_at,
            sources_summary=sources_summary,
            errors=errors,
            categories=score_result.categories,
            top_news=top_news,
            total_score=score_result.total_score,
            rating_label=score_result.rating_label,
        )

        fetch_log = {
            "fetch_time": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
            "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": round(result.duration_seconds, 2),
            "sources_summary": sources_summary,
            "errors": errors,
            "macro_calendar": macro.calendar_hints[:5],
            "total_score": score_result.total_score,
            "rating_label": score_result.rating_label,
        }

        update_state(
            categories=score_result.categories,
            total_score=score_result.total_score,
            top_news=top_news,
            btc_news=btc_news,
            sol_news=sol_news,
            eth_news=eth_news,
            macro_news=macro_news,
            fetch_log=fetch_log,
            last_fetch_time=finished_at,
            is_fetching=False,
        )

        append_fetch_log_row(
            fetch_time=finished_at,
            duration_sec=result.duration_seconds,
            success=result.success,
            error_count=len(errors),
            summary=sources_summary[:500],
        )
        append_news_snapshot(finished_at, top_news)
        def _cat_pts(name: str) -> float | None:
            for c in score_result.categories:
                if c.get("name") == name:
                    s = c.get("score")
                    return float(s) if s is not None else None
            return None

        upsert_4h_scores(
            finished_at,
            norm_scores=norm_scores,
            rating=score_result.rating_label,
            macro=_cat_pts("宏观数据"),
            regulation=_cat_pts("全球监管政策"),
            funding=_cat_pts("资金链上数据"),
            fundamentals=_cat_pts("ETH/SOL 币种基本面"),
        )

        append_score_history(
            finished_at,
            total_score=score_result.total_score,
            rating=score_result.rating_label,
            categories=score_result.categories,
        )

        logger.info(
            "本轮结束：总分 %.1f %s | 资讯 %d | 错误 %d | 耗时 %.2fs",
            score_result.total_score,
            score_result.rating_label,
            len(all_news),
            len(errors),
            result.duration_seconds,
        )
        return result

    except Exception as exc:
        finished_at = datetime.now()
        err_msg = f"{type(exc).__name__}: {exc}"
        errors = [err_msg]
        logger.exception("数据拉取失败")

        fetch_log = {
            "fetch_time": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
            "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": round((finished_at - started_at).total_seconds(), 2),
            "sources_summary": "拉取过程发生异常，请查看错误列表。",
            "errors": errors,
        }
        update_state(fetch_log=fetch_log, last_fetch_time=finished_at, is_fetching=False)

        append_fetch_log_row(
            fetch_time=finished_at,
            duration_sec=(finished_at - started_at).total_seconds(),
            success=False,
            error_count=1,
            summary=err_msg[:500],
        )
        return FetchResult(
            started_at=started_at,
            finished_at=finished_at,
            sources_summary=fetch_log["sources_summary"],
            errors=errors,
        )
    finally:
        set_fetching(False)
