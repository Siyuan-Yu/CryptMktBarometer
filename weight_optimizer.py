"""
动态权重优化 + 历史回测核心模块

功能：
  1. 根据近 7/30 天消息实际价格冲击，自适应四大模块权重
  2. 记录 TOP 资讯发布后 1h/4h/24h BTC/ETH/SOL 涨跌幅
  3. 历史回测：固定权重 vs 动态权重准确率对比

独立模块，不修改原有 scoring 算法，仅替换权重与总分合成方式。
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collectors.types import NewsItem
from core.config_loader import PROJECT_ROOT, load_config
from core.market_rating import rating_from_total_score
from scoring.constants import (
    FUNDAMENTALS_KEYWORDS,
    REGULATION_KEYWORDS,
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块键与固定权重（兼容旧版）
# ---------------------------------------------------------------------------
MODULE_MACRO = "macro"
MODULE_REGULATION = "regulation"
MODULE_FUNDING = "funding"
MODULE_FUNDAMENTALS = "fundamentals"

MODULE_ORDER = (MODULE_MACRO, MODULE_REGULATION, MODULE_FUNDING, MODULE_FUNDAMENTALS)

STATIC_WEIGHTS: dict[str, int] = {
    MODULE_MACRO: WEIGHT_MACRO,
    MODULE_REGULATION: WEIGHT_REGULATION,
    MODULE_FUNDING: WEIGHT_FUNDING,
    MODULE_FUNDAMENTALS: WEIGHT_FUNDAMENTALS,
}

WEIGHT_BOUNDS: dict[str, tuple[int, int]] = {
    MODULE_MACRO: (20, 50),
    MODULE_REGULATION: (10, 30),
    MODULE_FUNDING: (15, 35),
    MODULE_FUNDAMENTALS: (5, 20),
}

CATEGORY_TO_MODULE = {
    "宏观数据": MODULE_MACRO,
    "全球监管政策": MODULE_REGULATION,
    "资金链上数据": MODULE_FUNDING,
    "ETH/SOL 币种基本面": MODULE_FUNDAMENTALS,
}

# 突发事件关键词 → 提升对应模块
EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    MODULE_MACRO: (
        "cpi", "ppi", "nonfarm", "nfp", "fed", "fomc", "powell", "rate cut",
        "rate hike", "inflation", "jobs report", "treasury", "降息", "加息", "非农",
    ),
    MODULE_REGULATION: (
        "sec", "etf approval", "lawsuit", "ban", "regulation", "congress",
        "cftc", "approved", "rejected", "诉讼", "监管",
    ),
    MODULE_FUNDING: (
        "etf flow", "liquidation", "爆仓", "open interest", "inflow", "outflow",
        "whale", "funding rate",
    ),
    MODULE_FUNDAMENTALS: (
        "ethereum", "solana", "staking", "hack", "exploit", "mainnet upgrade",
    ),
}

SPIKE_THRESHOLD = 2.5
WEAK_THRESHOLD = 0.35
WEAK_STREAK = 3


@dataclass
class DynamicWeights:
    macro: int = 40
    regulation: int = 20
    funding: int = 25
    fundamentals: int = 15
    method: str = "static"
    updated_at: str = ""

    def as_dict(self) -> dict[str, int]:
        return {
            MODULE_MACRO: self.macro,
            MODULE_REGULATION: self.regulation,
            MODULE_FUNDING: self.funding,
            MODULE_FUNDAMENTALS: self.fundamentals,
        }

    def as_list_for_ui(self) -> list[dict[str, Any]]:
        labels = {
            MODULE_MACRO: "宏观数据",
            MODULE_REGULATION: "全球监管政策",
            MODULE_FUNDING: "资金链上数据",
            MODULE_FUNDAMENTALS: "ETH/SOL 币种基本面",
        }
        static = STATIC_WEIGHTS
        return [
            {
                "name": labels[k],
                "module": k,
                "weight": self.as_dict()[k],
                "static_weight": static[k],
                "delta": self.as_dict()[k] - static[k],
            }
            for k in MODULE_ORDER
        ]


@dataclass
class ModuleInfluence:
    """各模块市场影响力（最近窗口）。"""

    window_days: int
    scores: dict[str, float] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)

    def as_ui_rows(self) -> list[dict[str, Any]]:
        labels = {
            MODULE_MACRO: "宏观数据",
            MODULE_REGULATION: "全球监管政策",
            MODULE_FUNDING: "资金链上数据",
            MODULE_FUNDAMENTALS: "ETH/SOL 币种基本面",
        }
        return [
            {
                "name": labels[k],
                "influence": round(self.scores.get(k, 0.0), 2),
                "samples": self.sample_counts.get(k, 0),
            }
            for k in MODULE_ORDER
        ]


@dataclass
class BacktestResult:
    start_date: str
    end_date: str
    sample_days: int
    fixed_accuracy: float
    dynamic_accuracy: float
    fixed_correlation: float
    dynamic_correlation: float
    optimal_weights: DynamicWeights
    message: str = ""
    csv_path: str = ""

    def summary_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sample_days": self.sample_days,
            "fixed_accuracy": f"{self.fixed_accuracy:.1%}",
            "dynamic_accuracy": f"{self.dynamic_accuracy:.1%}",
            "fixed_correlation": round(self.fixed_correlation, 3),
            "dynamic_correlation": round(self.dynamic_correlation, 3),
            "optimal_weights": self.optimal_weights.as_dict(),
            "message": self.message,
            "csv_path": self.csv_path,
        }


# ---------------------------------------------------------------------------
# 分类与事件检测
# ---------------------------------------------------------------------------
def classify_news_module(title: str) -> str:
    lower = title.lower()
    if any(k in lower for k in EVENT_KEYWORDS[MODULE_MACRO]):
        return MODULE_MACRO
    if any(k in lower for k in REGULATION_KEYWORDS):
        return MODULE_REGULATION
    if any(k in lower for k in ("liquidation", "etf", "inflow", "outflow", "open interest")):
        return MODULE_FUNDING
    if any(k in lower for k in FUNDAMENTALS_KEYWORDS):
        return MODULE_FUNDAMENTALS
    return MODULE_REGULATION


def is_breaking_event(title: str, module: str) -> bool:
    lower = title.lower()
    return any(k in lower for k in EVENT_KEYWORDS.get(module, ()))


# ---------------------------------------------------------------------------
# 价格冲击测算
# ---------------------------------------------------------------------------
def measure_pending_impacts() -> int:
    """补全已发布满 24h 的消息的实际冲击值。"""
    from storage import impact_db, price_db

    price_db.init_schema()
    impact_db.init_schema()

    updated = 0
    for row in impact_db.list_pending_measurement():
        try:
            pub = datetime.fromisoformat(row["published_at"])
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        now = datetime.now(timezone.utc)
        if now < pub + timedelta(hours=24):
            continue

        cfg = load_config()
        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])

        a1 = price_db.composite_pct_change(pub, 1, syms)
        a4 = price_db.composite_pct_change(pub, 4, syms)
        a24 = price_db.composite_pct_change(pub, 24, syms)
        if a24 is None:
            continue

        impact_db.update_actual_impacts(
            row["id"],
            actual_1h=a1,
            actual_4h=a4,
            actual_24h=a24,
            composite_24h=a24,
        )
        updated += 1
    return updated


def register_top_news(news_items: list[NewsItem], top_display: list[dict]) -> None:
    """将 TOP 资讯写入冲击待测表。"""
    from storage import impact_db

    impact_db.init_schema()
    url_to_item = {n.url: n for n in news_items if n.url}
    for row in top_display:
        item = url_to_item.get(row.get("url", ""))
        title = row.get("title") or (item.title if item else "")
        if not title:
            continue
        mod = classify_news_module(title)
        pred = float(row.get("impact_score") or (item.impact_score if item else 0))
        pub = datetime.now(timezone.utc)
        if item and item.published_at:
            try:
                pub = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        impact_db.insert_news_pending(
            title=title,
            source=row.get("source", ""),
            url=row.get("url", ""),
            module=mod,
            published_at=pub,
            predicted_impact=pred,
            is_event=is_breaking_event(title, mod),
        )


# ---------------------------------------------------------------------------
# 动态权重计算
# ---------------------------------------------------------------------------
def _influence_to_raw_weights(influence_7: dict, influence_30: dict) -> dict[str, float]:
    raw: dict[str, float] = {}
    for mod in MODULE_ORDER:
        s7 = influence_7.get(mod, {})
        s30 = influence_30.get(mod, {})
        v7 = float(s7.get("abs_avg", 0)) + float(s7.get("event_ratio", 0)) * 2
        v30 = float(s30.get("abs_avg", 0))
        raw[mod] = v7 * 0.6 + v30 * 0.4 + 0.5
    return raw


def _apply_rules(weights: dict[str, float]) -> dict[str, float]:
    from storage import impact_db

    for mod in MODULE_ORDER:
        if impact_db.recent_weak_streak(mod, WEAK_THRESHOLD, WEAK_STREAK):
            weights[mod] *= 0.75
        stats = impact_db.module_influence_stats(7).get(mod, {})
        if float(stats.get("abs_avg", 0)) >= SPIKE_THRESHOLD:
            weights[mod] *= 1.35
        if float(stats.get("event_ratio", 0)) >= 0.25:
            weights[mod] *= 1.2
    return weights


def _normalize_weights(raw: dict[str, float]) -> DynamicWeights:
    bounded: dict[str, float] = {}
    for mod in MODULE_ORDER:
        lo, hi = WEIGHT_BOUNDS[mod]
        bounded[mod] = clamp(raw.get(mod, 1.0), lo, hi)

    total = sum(bounded.values())
    scaled = {m: bounded[m] / total * 100.0 for m in MODULE_ORDER}

    final: dict[str, int] = {}
    ints = {m: int(round(scaled[m])) for m in MODULE_ORDER}
    diff = 100 - sum(ints.values())
    ints[MODULE_MACRO] += diff

    for mod in MODULE_ORDER:
        lo, hi = WEIGHT_BOUNDS[mod]
        final[mod] = clamp(ints[mod], lo, hi)

    diff2 = 100 - sum(final.values())
    final[MODULE_MACRO] = clamp(final[MODULE_MACRO] + diff2, *WEIGHT_BOUNDS[MODULE_MACRO])

    return DynamicWeights(
        macro=final[MODULE_MACRO],
        regulation=final[MODULE_REGULATION],
        funding=final[MODULE_FUNDING],
        fundamentals=final[MODULE_FUNDAMENTALS],
        method="dynamic",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_dynamic_weights(cfg: dict | None = None) -> DynamicWeights:
    """根据近 7/30 天实际冲击计算动态权重。"""
    cfg = cfg or load_config()
    opt = cfg.get("weight_optimizer", {})
    if not opt.get("enabled", True):
        return _static_weights()

    from storage import impact_db

    impact_db.init_schema()
    inf7 = impact_db.module_influence_stats(int(opt.get("window_short_days", 7)))
    inf30 = impact_db.module_influence_stats(int(opt.get("window_long_days", 30)))

    total_samples = sum(int(inf7.get(m, {}).get("count", 0)) for m in MODULE_ORDER)
    if total_samples < int(opt.get("min_samples_for_dynamic", 5)):
        w = _static_weights()
        w.method = "static_insufficient_data"
        w.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return w

    raw = _influence_to_raw_weights(inf7, inf30)
    raw = _apply_rules(raw)
    return _normalize_weights(raw)


def _static_weights() -> DynamicWeights:
    return DynamicWeights(
        macro=STATIC_WEIGHTS[MODULE_MACRO],
        regulation=STATIC_WEIGHTS[MODULE_REGULATION],
        funding=STATIC_WEIGHTS[MODULE_FUNDING],
        fundamentals=STATIC_WEIGHTS[MODULE_FUNDAMENTALS],
        method="static",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def get_module_influence(window_days: int = 30) -> ModuleInfluence:
    from storage import impact_db

    stats = impact_db.module_influence_stats(window_days)
    scores = {m: float(stats.get(m, {}).get("abs_avg", 0)) for m in MODULE_ORDER}
    counts = {m: int(stats.get(m, {}).get("count", 0)) for m in MODULE_ORDER}
    return ModuleInfluence(window_days=window_days, scores=scores, sample_counts=counts)


# ---------------------------------------------------------------------------
# 与计分引擎对接：用动态权重合成总分
# ---------------------------------------------------------------------------
def apply_dynamic_total(
    categories: list[dict[str, Any]],
    weights: DynamicWeights,
) -> tuple[float, list[dict[str, Any]]]:
    """
    将原分项得分（按旧满分计量）归一化后，用动态权重合成总分。
    返回 (total_score, 更新后的 categories)
    """
    static_max = {
        MODULE_MACRO: WEIGHT_MACRO,
        MODULE_REGULATION: WEIGHT_REGULATION,
        MODULE_FUNDING: WEIGHT_FUNDING,
        MODULE_FUNDAMENTALS: WEIGHT_FUNDAMENTALS,
    }
    wmap = weights.as_dict()
    total = 0.0
    updated: list[dict[str, Any]] = []

    for cat in categories:
        mod = CATEGORY_TO_MODULE.get(cat["name"], MODULE_REGULATION)
        old_max = static_max[mod]
        raw_score = float(cat.get("score") or 0)
        norm = raw_score / old_max if old_max else 0.5
        norm = clamp(norm, 0.0, 1.0)
        w = wmap[mod]
        weighted_pts = round(norm * w, 1)
        total += weighted_pts
        new_cat = dict(cat)
        new_cat["weight"] = w
        new_cat["score"] = weighted_pts
        new_cat["norm_ratio"] = round(norm * 100, 1)
        updated.append(new_cat)

    total = round(clamp(total, 0, 100), 1)
    return total, updated


# ---------------------------------------------------------------------------
# 回测
# ---------------------------------------------------------------------------
def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx * dy == 0:
        return 0.0
    return num / (dx * dy)


def _direction_accuracy(pred: list[float], actual: list[float]) -> float:
    if not pred:
        return 0.0
    hits = sum(1 for p, a in zip(pred, actual) if (p >= 0) == (a >= 0))
    return hits / len(pred)


def _grid_search_weights(daily_module: dict[str, dict[str, float]], btc_returns: dict[str, float]) -> DynamicWeights:
    """在权重边界内网格搜索，最大化与 BTC 24h 收益相关性。"""
    best_corr = -2.0
    best = _static_weights()

    macro_range = range(20, 51, 10)
    reg_range = range(10, 31, 10)
    fund_range = range(15, 36, 10)

    days = sorted(btc_returns.keys())
    for ma in macro_range:
        for rg in reg_range:
            for fd in fund_range:
                fu = 100 - ma - rg - fd
                if not (5 <= fu <= 20):
                    continue
                w = DynamicWeights(macro=ma, regulation=rg, funding=fd, fundamentals=fu)
                preds = []
                acts = []
                for d in days:
                    mods = daily_module.get(d, {})
                    if d not in btc_returns:
                        continue
                    score = sum(mods.get(m, 0) * w.as_dict()[m] / 100.0 for m in MODULE_ORDER)
                    preds.append(score)
                    acts.append(btc_returns[d])
                if len(preds) < 5:
                    continue
                corr = _pearson(preds, acts)
                if corr > best_corr:
                    best_corr = corr
                    best = w
    best.method = "backtest_optimal"
    return best


def run_backtest(start_date: str, end_date: str, cfg: dict | None = None) -> BacktestResult:
    """
    历史回测：对比固定权重 vs 动态权重。
    需先回填价格：python weight_optimizer.py --backfill 2024-01-01 2025-05-31
    """
    cfg = cfg or load_config()
    from storage import impact_db

    impact_db.init_schema()
    rows = impact_db.list_impacts_between(f"{start_date}T00:00:00", f"{end_date}T23:59:59")

    if len(rows) < int(cfg.get("weight_optimizer", {}).get("backtest_min_samples", 10)):
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            sample_days=0,
            fixed_accuracy=0.0,
            dynamic_accuracy=0.0,
            fixed_correlation=0.0,
            dynamic_correlation=0.0,
            optimal_weights=_static_weights(),
            message=(
                f"样本不足（仅 {len(rows)} 条已测算冲击的资讯）。"
                "请先运行系统积累 TOP10 资讯，或执行 --backfill 回填价格后等待冲击测算。"
            ),
        )

    daily_module: dict[str, dict[str, float]] = {}
    btc_returns: dict[str, float] = {}

    for r in rows:
        day = r["published_at"][:10]
        mod = r["module"]
        imp = float(r["composite_24h"] or 0)
        daily_module.setdefault(day, {m: 0.0 for m in MODULE_ORDER})
        daily_module[day][mod] = daily_module[day].get(mod, 0) + imp
        btc_returns[day] = btc_returns.get(day, 0) + imp / max(1, len(MODULE_ORDER))

    days = sorted(daily_module.keys())
    fixed_w = _static_weights()
    dyn_w = compute_dynamic_weights(cfg)

    fixed_preds, dyn_preds, actuals = [], [], []
    for d in days:
        mods = daily_module[d]
        act = sum(mods.values()) / len(MODULE_ORDER)
        actuals.append(act)
        fixed_preds.append(sum(mods[m] * fixed_w.as_dict()[m] / 100 for m in MODULE_ORDER))
        dyn_preds.append(sum(mods[m] * dyn_w.as_dict()[m] / 100 for m in MODULE_ORDER))

    optimal = _grid_search_weights(daily_module, {d: btc_returns.get(d, actuals[i]) for i, d in enumerate(days)})

    result = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        sample_days=len(days),
        fixed_accuracy=_direction_accuracy(fixed_preds, actuals),
        dynamic_accuracy=_direction_accuracy(dyn_preds, actuals),
        fixed_correlation=_pearson(fixed_preds, actuals),
        dynamic_correlation=_pearson(dyn_preds, actuals),
        optimal_weights=optimal,
        message=f"回测完成，有效交易日 {len(days)} 天，资讯冲击记录 {len(rows)} 条",
    )

    result.csv_path = _save_backtest_csv(result, days, daily_module, fixed_preds, dyn_preds, actuals)
    _save_backtest_summary_json(result)
    return result


def _log_dir() -> Path:
    cfg = load_config()
    rel = cfg.get("storage", {}).get("log_dir", "data/logs")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_backtest_csv(
    result: BacktestResult,
    days: list[str],
    daily_module: dict,
    fixed_preds: list[float],
    dyn_preds: list[float],
    actuals: list[float],
) -> str:
    path = _log_dir() / "backtest_detail.csv"
    write_header = not path.exists()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "date",
                "actual_avg_impact",
                "fixed_pred",
                "dynamic_pred",
                "macro_impact",
                "reg_impact",
                "fund_impact",
                "funda_impact",
            ]
        )
        for i, d in enumerate(days):
            m = daily_module[d]
            w.writerow(
                [
                    d,
                    round(actuals[i], 4),
                    round(fixed_preds[i], 4),
                    round(dyn_preds[i], 4),
                    round(m.get(MODULE_MACRO, 0), 4),
                    round(m.get(MODULE_REGULATION, 0), 4),
                    round(m.get(MODULE_FUNDING, 0), 4),
                    round(m.get(MODULE_FUNDAMENTALS, 0), 4),
                ]
            )
    summary_path = _log_dir() / "backtest_summary.csv"
    write_h = not summary_path.exists()
    with open(summary_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "run_at",
                "start",
                "end",
                "sample_days",
                "fixed_acc",
                "dynamic_acc",
                "fixed_corr",
                "dynamic_corr",
                "opt_macro",
                "opt_reg",
                "opt_fund",
                "opt_funda",
            ],
        )
        if write_h:
            w.writeheader()
        ow = result.optimal_weights
        w.writerow(
            {
                "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "start": result.start_date,
                "end": result.end_date,
                "sample_days": result.sample_days,
                "fixed_acc": round(result.fixed_accuracy, 4),
                "dynamic_acc": round(result.dynamic_accuracy, 4),
                "fixed_corr": round(result.fixed_correlation, 4),
                "dynamic_corr": round(result.dynamic_correlation, 4),
                "opt_macro": ow.macro,
                "opt_reg": ow.regulation,
                "opt_fund": ow.funding,
                "opt_funda": ow.fundamentals,
            }
        )
    return str(summary_path)


def _save_backtest_summary_json(result: BacktestResult) -> None:
    path = _log_dir() / "backtest_latest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.summary_dict(), f, ensure_ascii=False, indent=2)


def load_latest_backtest() -> dict[str, Any]:
    path = _log_dir() / "backtest_latest.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 定时任务入口
# ---------------------------------------------------------------------------
def run_weight_pipeline(cfg: dict | None = None) -> dict[str, Any]:
    """价格同步 + 冲击补全 + 权重重算（每 6 小时调用）。"""
    cfg = cfg or load_config()
    opt = cfg.get("weight_optimizer", {})
    if not opt.get("enabled", True):
        return {"skipped": True}

    from collectors.price_hourly import sync_recent_hours

    syms = opt.get("price_symbols", ["BTC", "ETH", "SOL"])
    hours = int(opt.get("price_sync_hours", 168))
    price_counts = sync_recent_hours(syms, hours=hours)
    measured = measure_pending_impacts()
    weights = compute_dynamic_weights(cfg)
    influence = get_module_influence(int(opt.get("window_long_days", 30)))

    payload = {
        "weights": weights,
        "influence": influence,
        "price_sync": price_counts,
        "impacts_updated": measured,
    }
    _persist_optimizer_state(payload)
    return payload


def _persist_optimizer_state(payload: dict) -> None:
    from core.state_store import update_state

    w: DynamicWeights = payload["weights"]
    inf: ModuleInfluence = payload["influence"]
    update_state(
        weight_optimizer={
            "dynamic_weights": w.as_list_for_ui(),
            "weights_method": w.method,
            "weights_updated_at": w.updated_at,
            "module_influence": inf.as_ui_rows(),
            "influence_window_days": inf.window_days,
            "backtest": load_latest_backtest(),
            "price_sync": payload.get("price_sync"),
            "impacts_updated": payload.get("impacts_updated"),
        },
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def rebuild_impacts_from_news_csv() -> int:
    """从 data/logs/news_snapshot.csv 重建待测算记录并尝试补全冲击。"""
    import csv

    from storage import impact_db, price_db

    price_db.init_schema()
    impact_db.init_schema()
    path = _log_dir() / "news_snapshot.csv"
    if not path.exists():
        logger.warning("未找到 %s", path)
        return 0
    n = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "")
            if not title:
                continue
            mod = classify_news_module(title)
            try:
                pub = datetime.strptime(row["fetch_time"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pub = datetime.now(timezone.utc)
            pred = float(row.get("impact_score") or 0)
            impact_db.insert_news_pending(
                title=title,
                source=row.get("source", ""),
                url=row.get("url", ""),
                module=mod,
                published_at=pub,
                predicted_impact=pred,
                is_event=is_breaking_event(title, mod),
            )
            n += 1
    return n + measure_pending_impacts()


def main() -> None:
    parser = argparse.ArgumentParser(description="动态权重与回测工具")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"), help="回填历史K线 YYYY-MM-DD")
    parser.add_argument("--backtest", nargs=2, metavar=("START", "END"), help="运行回测")
    parser.add_argument("--recalc", action="store_true", help="立即重算动态权重")
    parser.add_argument("--sync-prices", action="store_true", help="同步最近价格")
    parser.add_argument("--rebuild-impacts", action="store_true", help="从 news_snapshot.csv 重建冲击样本")
    args = parser.parse_args()
    cfg = load_config()

    if args.backfill:
        from collectors.price_hourly import backfill_history

        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])
        print("回填价格…", backfill_history(syms, args.backfill[0], args.backfill[1]))
        return

    if args.sync_prices:
        from collectors.price_hourly import sync_recent_hours

        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])
        print(sync_recent_hours(syms))
        return

    if args.backtest:
        r = run_backtest(args.backtest[0], args.backtest[1], cfg)
        print(json.dumps(r.summary_dict(), ensure_ascii=False, indent=2))
        return

    if args.recalc:
        print(json.dumps(asdict(run_weight_pipeline(cfg)), default=str, ensure_ascii=False, indent=2))
        return

    if args.rebuild_impacts:
        print(f"已处理/更新冲击记录: {rebuild_impacts_from_news_csv()} 条")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
